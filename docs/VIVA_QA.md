# Viva questions and answers (from this codebase)

Short answers, with the file to open if asked to show it.

## Concepts

1. **Steganography vs cryptography vs steganalysis?**
   Cryptography hides *what* a message says; steganography hides that a message *exists*; steganalysis tries to
   *detect* hidden data. We use all three: AES-GCM (crypto), LSB embedding (stego), chi-square/RS/SPA/CNN
   (steganalysis).

2. **Why do we need both stego and crypto?**
   Steganography alone is only obscurity: once found, the message is readable. Encrypting first means a found
   payload is still secret, and signing means it cannot be forged. (`core/pipeline.py`)

3. **LSB replacement vs LSB matching?**
   Replacement overwrites the least significant bit: `v' = (v & 0xFE) | b`, so values only move within the pair
   (2k, 2k+1), which chi-square, RS and SPA exploit. Matching changes the value by ±1 when the bit differs,
   crossing pairs and removing that signature. Extraction is the same for both. (`stego/lsb_replace.py`,
   `lsb_match.py`)

4. **Why PNG and not JPEG?**
   JPEG is lossy: quantisation rewrites LSBs, destroying the payload. We accept PNG/BMP/PGM for embedding and
   reject JPEG with an explanation. JPEG is allowed for detection with a warning. (`stego/image_io.py`)

5. **What does bpp mean and why use it?**
   Bits per pixel: embedded bits ÷ number of pixels. It makes payloads comparable across image sizes and is the
   convention in the literature. Our grid is 0.05, 0.1, 0.2, 0.4, 1.0.

6. **What is the capacity of a cover?**
   Keyed mode: `samples − 128` bits for scatter (128 are the stego salt); minus a 104-bit header; minus 128 bytes
   of packet overhead for the plaintext. (`stego/embed.py: maximum_payload_bytes`)

## Cryptography

7. **Describe the packet.**
   `magic, version, flags, kdf_id, reserved, sender_fp(8), salt(16), nonce(12), ct_len(4), ciphertext+tag,
   Ed25519 signature(64)`: 128 bytes of overhead plus the plaintext. (`crypto/packet.py`)

8. **Why Argon2id instead of PBKDF2?**
   PBKDF2 is only CPU-hard, so GPUs/ASICs guess passwords cheaply. Argon2id is memory-hard (we use 64 MiB, 3
   passes, 4 lanes), making parallel guessing expensive, and the "id" variant resists both side-channel and
   time-memory trade-off attacks. (RFC 9106; `crypto/kdf.py`)

9. **Why a unique salt and nonce per message?**
   A random 16-byte salt makes every message key different even for the same password. AES-GCM must never
   reuse a (key, nonce) pair; here the key is already unique per message and the nonce is random 12 bytes.

10. **What happens if a GCM nonce is reused?**
    The keystream repeats, so XORing two ciphertexts leaks the XOR of the plaintexts, and the authentication
    key can be recovered, enabling forgeries. That is why we generate fresh values with `os.urandom`.

11. **Why sign *and* use an AEAD?**
    GCM gives confidentiality and integrity to anyone holding the password (including an insider). The Ed25519
    signature adds *sender authentication and non-repudiation*, and lets the receiver reject forgeries cheaply
    **before** running Argon2 and AES.

12. **Why verify before decrypt?**
    So unauthenticated data never reaches the decryption path (no oracle, no wasted work, no chosen-ciphertext
    games). In `receiver_pipeline` the order is parse → fingerprint → verify signature → derive key → decrypt,
    and a test asserts decryption is never attempted when verification fails.

13. **What is the AAD?**
    The packet header from `magic` through `nonce` is authenticated as associated data, so changing flags,
    salt or sender fingerprint breaks the tag even though the header is not encrypted.

14. **What does the manifest protect?**
    The stego pixel hash, dimensions, method, mode, payload size and sender fingerprint, signed with Ed25519
    over canonical JSON. Change one pixel anywhere and check A fails, even when the payload still extracts.
    (`crypto/manifest.py`, `/api/verify`)

15. **How do you compare secrets safely?**
    With constant-time comparisons (`hmac.compare_digest`) for hashes, fingerprints and MACs, so timing does not
    leak how many leading bytes matched.

16. **How are private keys stored?**
    Only exported as password-encrypted PKCS#8 PEM (`BestAvailableEncryption`). The server never keeps keys,
    passwords, images or messages.

## Steganography design

17. **Why a keyed scatter?**
    Sequential embedding concentrates changes in the top rows, which is trivially detectable (progressive
    chi-square) and the magic bytes sit in plain LSBs. Keyed mode spreads bits over the whole image in an order
    only the key-holder can recompute.

18. **How is the permutation made reproducible?**
    From a ChaCha20 keystream (key from HKDF), interpreted as 64-bit integers and `argsort`-ed with a stable
    sort. We never use NumPy's RNG for anything the receiver must reproduce, because its stream can change
    between versions. (`stego/scatter.py`, `keystream.py`)

19. **What is whitening and why?**
    The header+packet bytes are XORed with another ChaCha20 stream before embedding so the written bits look
    like fair coin flips instead of structured data.

20. **Why does wrong key look like "no hidden data"?**
    The receiver reads the stego salt, derives keys, checks the 13-byte header (magic, version, CRC). A wrong
    key yields garbage, so the magic check fails: the same `NO_HIDDEN_DATA` as a clean image, giving an attacker
    no oracle.

## Steganalysis

21. **How does the chi-square attack work?**
    Westfeld & Pfitzmann (1999): LSB replacement with random data equalises the counts of each value pair
    (2k, 2k+1). The statistic compares observed counts with the equalised expectation; a high p-value means
    "suspiciously equal". (`classical/chi_square.py`)

22. **How does RS analysis work?**
    Fridrich, Goljan & Du (2001): split the image into groups, measure a smoothness function, apply flipping
    masks M and −M, and count regular vs singular groups. In clean images R(M) ≈ R(−M); embedding breaks that,
    and a quadratic estimate gives the embedded length. (`classical/rs.py`)

23. **How does Sample Pair Analysis work?**
    Dumitrescu, Wu & Wang (2003): pairs of adjacent samples fall into sets whose sizes obey statistical
    relationships in natural images; LSB replacement disturbs them in a predictable way, so the embedding rate
    can be solved for. (`classical/spa.py`)

24. **Why a fixed high-pass first layer in the CNN?**
    Stego noise is tiny compared with image content. A fixed KV 5×5 kernel removes content and exposes the
    noise residual, so the network learns from the residual instead of wasting capacity learning to suppress
    content. It is frozen (`requires_grad = False`). (`deep/filters.py`)

25. **Why no early pooling?**
    Pooling averages away the faint, high-frequency stego signal. The first stages use residual 3×3 blocks with
    no pooling (SRNet design insight); downsampling begins only after features are extracted. (`deep/model.py`)

26. **Why pair batching?**
    Each cover and its stego version go in the same batch. The network then sees the *difference* caused by
    embedding rather than differences between unrelated images, which stabilises training. (`deep/dataset.py`)

27. **What are ROC, AUC and P_E?**
    ROC plots true-positive rate against false-positive rate over all thresholds; AUC is the area under it (0.5 =
    guessing, 1 = perfect). P_E = min over thresholds of ½(P_FA + P_MD), the standard steganalysis error: 0.5 is
    chance, 0 is perfect. We also report TPR at 1% FPR and bootstrap 95% confidence intervals.

28. **Why split by cover ID?**
    A cover and all its stego versions must stay in one split. Otherwise the model sees the same image in
    training and testing and the test numbers are inflated. We assert zero overlap in a test.

29. **Why only flips and 90° rotations for augmentation?**
    Resizing, blur, JPEG or brightness changes destroy the stego signal or create artefacts the model could learn
    instead of steganography. Flips/rotations preserve pixel statistics.

30. **What is the mismatch experiment?**
    Train the CNN on LSB replacement only and test on LSB matching. The drop in performance measures how poorly
    a detector generalises to an embedding method it has not seen.

31. **How is the final verdict produced?**
    From a validation-fitted weighted average of the classical model and CNN, with thresholds chosen on
    validation (balanced = max Youden's J; low-false-alarm = at most 1% FPR). If the ensemble is unavailable the
    best single trained detector decides and the UI says so. (`steganalysis/service.py`, `evaluation.py`)

32. **How do you calibrate the CNN?**
    Temperature scaling: a single scalar fitted on validation logits by minimising binary cross-entropy, so
    reported probabilities reflect real frequencies.

## Results and honesty

33. **Where do the numbers in the UI come from?**
    Only `backend/results/metrics.json`, produced by `scripts/evaluate.py` on fixed, seeded, cover-disjoint test
    images. If a model is not trained the UI says "not trained" instead of showing placeholder values.

34. **Where does the detector fail?**
    At low payloads (≈0.05 bpp), for LSB matching against chi-square/RS/SPA, on cameras different from BOSSbase,
    on RGB images (trained on grayscale). Real STC embedding is implemented for S-UNIWARD and HILL, but detector
    performance on those real messages has not yet been measured; the stored scores use simulator outputs.

## Engineering and ethics

35. **How do you stop abuse of the API?**
    10 MB body cap checked before parsing, pixel limits read from the header (4 MP embed, 16 MP detect),
    decode-based validation, Pillow bomb guard, 30 POST/min/IP with `Retry-After`, CORS allow-list, and security
    headers. (`api/limits.py`)

36. **How do you ensure secrets are not logged?**
    The access log records only method, path, status and latency; validation errors report field names, never
    values; a test captures all logs during embed/extract and asserts none of the passwords, plaintext or PEM
    text appear.

37. **Why is the server stateless?**
    Uploads, messages and keys are processed in memory and discarded. We raise Starlette's multipart spool limit
    so uploads never spill to temp files on disk.

38. **Why never pass the stego image through a `<canvas>` for download?**
    Canvas round-trips can change pixel values (colour management, alpha premultiplication) and destroy hidden
    bits. The PNG arrives as base64 and is decoded straight into a Blob. The Tamper test page is the one place the
    canvas is used, deliberately, to attack an image.

39. **What are the main limitations?**
    LSB does not survive JPEG/resizing; Python cannot guarantee memory zeroization; detectors are probabilistic;
    verification reasons are shown for teaching; replay of an old valid image is not prevented.

40. **Is it ethical to build this?**
    Both sides are published, dual-use techniques. The project is educational, uses textbook methods that its own
    detectors catch at moderate payloads, states its limits, and warns that detector output is not evidence
    against a person. See `docs/ETHICS.md`.

## Added techniques

41. **How does 2-LSB differ from LSB, and what does it cost?**
    Each selected sample carries two message bits instead of one, so capacity doubles, but each change can be up to
    ±3 instead of ±1, so distortion per embedded bit is larger and the embedding is easier to see statistically.
    For the same payload only half as many samples change, but by more. (`stego/lsb_replace.py`, tests in
    `test_lsb2.py` check the expected distortion MSE ≈ 1.25 · bpp against 0.5 · bpp for 1-bit LSB.)

42. **How does the receiver know whether 1-bit or 2-LSB was used?**
    It either is told, or it tries both: `extract_auto` reads the stream header at each bit depth and keeps the one whose
    magic bytes, version and CRC32 validate. A wrong depth reads garbage, so it fails the CRC (false accept 2^-32),
    and every failure is the same `NO_HIDDEN_DATA`, so this leaks nothing.

43. **How do S-UNIWARD and HILL carry a message here?**
    Their cost maps assign higher change cost to smoother regions. STC encodes the signed packet into ±1 changes
    while favoring lower-cost samples. The receiver recomputes keyed positions and decodes the STC syndrome without
    the cover. The separate simulator remains for detector experiments and does not carry a message.

44. **Do the saved detector scores describe real STC messages?**
    No. The 35 saved conditions include simulator-generated S-UNIWARD and HILL samples. Real STC messages now
    round-trip, but detection on those embeddings has not been evaluated. The existing scores must not be used to
    claim how a detector performs on real STC messages.

45. **Why evaluate on unseen techniques without retraining?**
    It answers a different question: how well does a detector trained on one technique transfer to another? Retraining
    on a mix would raise the numbers but would not tell us that. Thresholds and ensemble weights stay fixed on the
    trained techniques' validation data, so nothing is tuned on the new test sets.

