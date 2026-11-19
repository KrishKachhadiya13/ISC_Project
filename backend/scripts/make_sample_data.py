"""Generate 30 small synthetic grayscale demo covers without external assets."""

import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw

DEFAULT_SAMPLE_COUNT = 30
DEFAULT_SIZE = 256
DEFAULT_SEED = 1337


def create_sample_images(
    output: Path,
    count: int = DEFAULT_SAMPLE_COUNT,
    size: int = DEFAULT_SIZE,
    seed: int = DEFAULT_SEED,
) -> list[Path]:
    """Create deterministic synthetic grayscale images for smoke tests and demos.

    These procedural images are not natural photographs and are not suitable
    for training or evaluating statistical steganalysis models.
    """
    if count < 1 or size < 16 or seed < 0:
        raise ValueError("Count, size, and seed are outside supported limits.")
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index in range(count):
        rng = random.Random(seed + index)
        base = rng.randint(40, 130)
        pixels = [
            max(
                0,
                min(
                    255,
                    base + int(45 * y / size) + int(20 * x / size) + rng.randint(-24, 24),
                ),
            )
            for y in range(size)
            for x in range(size)
        ]
        image = Image.new("L", (size, size))
        image.putdata(pixels)
        draw = ImageDraw.Draw(image)
        for _ in range(12):
            x = rng.randrange(size)
            y = rng.randrange(size)
            radius = rng.randrange(max(2, size // 40), max(3, size // 8))
            tone = rng.randrange(15, 241)
            draw.ellipse((x, y, x + radius, y + radius), fill=tone)
        path = output / f"synthetic_{index:02d}.png"
        image.save(path, format="PNG", compress_level=6)
        paths.append(path)
    return paths


def main() -> int:
    """Write the default demo sample collection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/sample"))
    parser.add_argument("--count", type=int, default=DEFAULT_SAMPLE_COUNT)
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    paths = create_sample_images(args.out, args.count, args.size, args.seed)
    print(f"Generated {len(paths)} synthetic demo covers in {args.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
