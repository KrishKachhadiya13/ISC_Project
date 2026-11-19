"""Demo-friendly command-line interface for StegaGuard workflows."""

import argparse
import getpass
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.core.crypto import keys
from app.core.crypto.exceptions import CryptoError
from app.core.pipeline import (
    PipelineStage,
    receiver_pipeline,
    sender_pipeline,
    verify_pipeline,
)
from app.core.stego.exceptions import StegoError


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for keygen, embed, extract, and verify."""
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Create and verify educational StegaGuard stego messages.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    keygen = commands.add_parser("keygen", help="Generate Ed25519 sender keys.")
    keygen.add_argument("--private-key", required=True, type=Path)
    keygen.add_argument("--public-key", required=True, type=Path)

    embed = commands.add_parser("embed", help="Encrypt, sign, and hide a message.")
    embed.add_argument("--cover", required=True, type=Path)
    message = embed.add_mutually_exclusive_group(required=True)
    message.add_argument("--message")
    message.add_argument("--message-file", type=Path)
    embed.add_argument("--private-key", required=True, type=Path)
    embed.add_argument("--output", required=True, type=Path)
    embed.add_argument("--manifest", required=True, type=Path)
    embed.add_argument("--mode", choices=("keyed", "sequential"), default="keyed")
    embed.add_argument("--method", choices=("lsb_replace", "lsb_match"), default="lsb_replace")

    extract = commands.add_parser("extract", help="Verify and recover an embedded message.")
    extract.add_argument("--image", required=True, type=Path)
    extract.add_argument("--public-key", required=True, type=Path)
    extract.add_argument("--mode", choices=("keyed", "sequential"), default="keyed")
    extract.add_argument("--output", type=Path, help="Required for an embedded file payload.")

    verify = commands.add_parser("verify", help="Check pixel hash and both signatures.")
    verify.add_argument("--image", required=True, type=Path)
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--public-key", required=True, type=Path)
    verify.add_argument("--mode", choices=("keyed", "sequential"), default="keyed")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one CLI command and return a process exit status."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "keygen":
            return _keygen(args.private_key, args.public_key)
        if args.command == "embed":
            return _embed(args)
        if args.command == "extract":
            return _extract(args)
        if args.command == "verify":
            return _verify(args)
        raise ValueError(f"Unknown command: {args.command}")
    except (CryptoError, StegoError, OSError, ValueError) as exc:
        print(f"StegaGuard: {exc}", file=sys.stderr)
        return 1


def _keygen(private_path: Path, public_path: Path) -> int:
    """Generate an encrypted private-key PEM and a public-key PEM."""
    password = getpass.getpass("Private-key password (minimum 8 characters): ")
    private_key, public_key = keys.generate_keypair()
    private_path.write_text(keys.export_private_key_pem(private_key, password), encoding="utf-8")
    public_path.write_text(keys.export_public_key_pem(public_key), encoding="utf-8")
    print(json.dumps({"fingerprint": keys.fingerprint(public_key)}))
    return 0


def _embed(args: argparse.Namespace) -> int:
    """Run the sender pipeline and save its PNG plus detached manifest."""
    message = args.message
    is_file = args.message_file is not None
    filename = args.message_file.name if is_file else None
    if is_file:
        message = args.message_file.read_bytes()
    password = getpass.getpass("Message password (minimum 8 characters): ")
    key_password = getpass.getpass("Private-key password: ")
    stego_passphrase = password if args.mode == "keyed" else None
    result = sender_pipeline(
        args.cover.read_bytes(),
        message,
        password,
        args.private_key.read_bytes(),
        key_password,
        method=args.method,
        mode=args.mode,
        stego_passphrase=stego_passphrase,
        is_file=is_file,
        filename=filename,
    )
    stego_png, manifest_data, metrics, _diff_png, warnings = result
    args.output.write_bytes(stego_png)
    args.manifest.write_text(
        json.dumps(manifest_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"metrics": metrics, "warnings": warnings}, ensure_ascii=False))
    return 0


def _extract(args: argparse.Namespace) -> int:
    """Run receiver verification and reveal content only after every stage passes."""
    public_key = keys.load_public_key_pem(args.public_key.read_bytes())
    password = getpass.getpass("Message password: ")
    result = receiver_pipeline(
        args.image.read_bytes(),
        password,
        public_key,
        mode=args.mode,
        stego_passphrase=password if args.mode == "keyed" else None,
    )
    if not result.verified or result.payload is None:
        print(
            json.dumps(
                {"verified": False, "stages": [_stage_dict(stage) for stage in result.stages]}
            ),
            file=sys.stderr,
        )
        return 1
    if result.payload.is_file:
        if args.output is None:
            print("StegaGuard: use --output to save the verified file payload.", file=sys.stderr)
            return 1
        args.output.write_bytes(result.payload.data)
        print(json.dumps({"verified": True, "file": str(args.output)}))
    else:
        print(result.payload.text)
    return 0


def _verify(args: argparse.Namespace) -> int:
    """Run detached-manifest and embedded-packet integrity verification."""
    public_key = keys.load_public_key_pem(args.public_key.read_bytes())
    password = getpass.getpass("Stego passphrase: ") if args.mode == "keyed" else None
    manifest_data = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest_data, dict):
        raise ValueError("Manifest must contain a JSON object.")
    result = verify_pipeline(
        args.image.read_bytes(),
        manifest_data,
        public_key,
        mode=args.mode,
        stego_passphrase=password,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["overall_ok"] else 1


def _stage_dict(stage: PipelineStage) -> dict[str, str]:
    """Convert a pipeline stage to its small JSON representation."""
    return {
        "name": stage.name,
        "status": stage.status,
        "detail": stage.detail,
    }


if __name__ == "__main__":
    raise SystemExit(main())
