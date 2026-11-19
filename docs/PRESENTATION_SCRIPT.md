# StegaGuard: full presentation script (3 speakers, about 22 minutes plus questions)

**How to read this.** Every segment has three parts: **ON SCREEN** (what the person at the keyboard does),
**SAY** (words to speak, in plain language) and **WHAT THE OUTPUT MEANS** (how to explain what the page shows,
so nobody just reads numbers). Say it in your own words; the SAY text is a guide, not a poem.

The three requirements of the brief are called out as **[AI]**, **[INFO SECURITY]**, **[CRYPTOGRAPHY]** and the
application area as **[MULTIMEDIA]**. Say these tags out loud at least once in each segment, so the examiners can
tick them off. (Confirm the exact wording of your brief; the mapping table in Part 0 is the one to adjust.)

---

## The team and the split

| Speaker | Role | Parts | Time | Drives the laptop |
|---|---|---|---|---|
| **Person 1: "The message"** | Foundations and cryptography | Opening, requirements, Home, Hide, Extract, How it works | about 9 min | Yes, for Parts 0 to 4 |
| **Person 2: "The detector"** | AI and steganalysis | Detect, Compare detectors, Batch scan, how the models work | about 7 min | Yes, for Part 5 |
| **Person 3: "The proof"** | Information security and engineering | Tamper test, architecture, security rules, testing, limits and ethics, close | about 6 min | Yes, for Part 6 |

Hand the laptop over at each handoff line. Only one person speaks at a time; the other two watch the screen and
stay quiet. If something breaks, Person 3 handles the recovery plan at the bottom.

### Minute map

| Time | Part | Speaker |
|---|---|---|
| 0:00 to 3:00 | 0. What problem we solve, and the three requirements | Person 1 |
| 3:00 to 4:00 | 1. Home page | Person 1 |
| 4:00 to 7:30 | 2. Hide a message (sender) | Person 1 |
| 7:30 to 9:30 | 3. Extract and verify (receiver) | Person 1 |
| 9:30 to 10:00 | 4. How it works (packet format) | Person 1 |
| 10:00 to 13:00 | 5a. Detect (defender) | Person 2 |
| 13:00 to 14:30 | 5b. Compare detectors (arms race) | Person 2 |
| 14:30 to 15:30 | 5c. Batch scan, and how the models work | Person 2 |
| 15:30 to 17:30 | 6a. Tamper test | Person 3 |
| 17:30 to 19:30 | 6b. Architecture and security rules | Person 3 |
| 19:30 to 21:00 | 6c. Honest limits, ethics, About page | Person 3 |
| 21:00 to 22:00 | 7. Close | Person 3 (all stand) |

---

## Before you start (checklist for Person 3, 10 minutes before)

1. App running: open `http://localhost:5173/hide?demo=1`. The violet **Presenter mode** banner must be visible,
   and the green **Server connected** badge in the header.
2. **Never reload and never type a new address** during the demo. Reloading clears the in-memory demo keys. Use
   the links in the top bar only.
3. Run the whole flow once in private: **Hide** with the long message, **Extract**, **Detect**. Check the
   cover scans "Not flagged" and the long-message image scans "Hidden data suspected".
4. Zoom the browser to 110% to 125% so the back row can read it. Dark theme is the default; keep it.
5. Have `docs/VIVA_QA.md` open in a second window for questions.
6. Say out loud which parts of the system are trained (the neural network and the feature classifier are; the
   statistical tests are not). Never claim something is trained that is not.

---

# Part 0. The problem and the three requirements (Person 1, 3 minutes)

**ON SCREEN:** the Home page, hero visible. Do not click anything yet.

**SAY:**

> Good morning. Our project is called **StegaGuard**. Let me start with three words that sound alike.
>
> **Cryptography** hides *what* a message says. If you encrypt a message, everyone can see you are sending
> something secret, but nobody can read it.
>
> **Steganography** hides *that* a message exists at all. We put the message inside an ordinary-looking picture.
> Nobody even knows to look. It is the difference between a locked box and a box nobody knows exists.
>
> **Steganalysis** is the opposite side: the defender, who looks at a picture and asks, "is something hidden in
> here?" It is detective work done with statistics and, in our project, **artificial intelligence**.
>
> A single tool that does only one of these has a weakness. Hiding without encryption: if someone finds it,
> they read it. Encryption without a signature: someone can swap the picture and you cannot tell. And hiding
> without ever asking how detectable it is means you are guessing that you are safe.
>
> So StegaGuard does all of it in one system, for **images**, which is our **multimedia** domain. A sender
> encrypts and signs a message, then hides it in a picture. A receiver checks the signature **first**, and only
> then decrypts. And a defender can scan any picture and estimate whether it is hiding something.

**Show this table (on a slide, or say it):**

| Requirement of the brief | Where it lives in StegaGuard | What you will see in the demo |
|---|---|---|
| **[CRYPTOGRAPHY]** | Argon2id key derivation, AES-256-GCM encryption, Ed25519 digital signatures, signed integrity manifest | Hide and Extract pages, the "How it works" packet table |
| **[INFO SECURITY]** | Verify-before-decrypt, tamper detection, input validation, rate limiting, stateless server, threat model, ethics | Extract failures, Tamper test, Architecture, About |
| **[AI]** | Statistical tests, a trained feature classifier, a trained neural network (CNN), and a combined verdict with a heat map | Detect, Compare detectors, Batch scan |
| **[MULTIMEDIA]** | Digital images, pixels and bit planes, image-quality measures, why lossless versus lossy matters | Hide result (before/after, difference map), Home animation |

> We will walk through the live website, page by page. The order is the order of a real message's life:
> hide it, receive it, try to detect it, try to break it.

---

# Part 1. Home page (Person 1, 1 minute)

**ON SCREEN:** stay on Home. Point at the hero, the animation, the three numbers, then the "path of a message".

**SAY and WHAT THE OUTPUT MEANS:**

- **The animation (bit plane).** "Every pixel is a number from 0 to 255, so it is eight binary digits. The
  *last* digit, the least significant bit, changes the brightness by one out of 255. You cannot see that. This
  picture shows only that last layer. On the right side, an untouched image has regular, smooth stripes. On the
  left, where a message is hidden, it turns to random noise. That is the whole trick, and it is also the
  weakness the defender uses."
- **The three numbers: 5 hiding techniques, 3 detectors, 6 verification steps.** "Three detectors look at an
  image, and six checks stand between a hidden package and a decrypted message. The five techniques are three
  LSB variants that can carry a real message, plus S-UNIWARD and HILL, two advanced methods. We will say more
  about those later." *(Before the talk, check the Hide page's method list. On the build machine all five work, because the
  STC package is installed; on another laptop without it, S-UNIWARD and HILL show a clear "not installed"
  message. See "Honest limits" in Part 6.)*
- **The path of a message strip.** "Encrypt, sign, hide, verify, decrypt. Five steps. Notice the order on the
  receiving side: **verify before decrypt**. We will come back to why."

**Handoff within Person 1:** click **Hide a message** in the top bar.

---

# Part 2. Hide a message: the sender (Person 1, 3.5 minutes)

**ON SCREEN:** Hide page. Click **Fill demo cover, message and keys** (the violet button). It loads a
cover, a message, passwords and a fresh key pair, and jumps to the last step. Walk back through the four steps
as you speak, then press **Hide message**.

### Step 1 (Cover)

**SAY:** "This is the cover: a plain photograph. The page shows a **capacity meter**: how many bytes this picture
can carry. It is computed from the number of pixels, minus a small fixed overhead for the keys and headers.
The more you hide, the more pixels you change."

**WHAT THE OUTPUT MEANS:** capacity is the hard limit. Bigger message means more changed pixels, which means
easier to detect. That tension (more capacity, less safety) is the central trade-off of steganography.

### Step 2 (Message)

**SAY:** "The sender types a message, or attaches a file, and a password. The password does not hide the picture;
it protects the message through encryption **[CRYPTOGRAPHY]**."

### Step 3 (Keys and method)

**SAY:** "Two keys here, and it is worth being exact about them:
- A **password** is turned into an encryption key with **Argon2id**. It is deliberately slow and memory-hungry
  (64 megabytes), so someone guessing passwords has to pay that cost for every single guess.
- An **Ed25519 key pair**: a private key that signs, and a public key that anyone can use to check the
  signature. The private key is downloaded *encrypted* with its own password; the server never keeps it.

The **method** is how the bits go into the picture: replacement overwrites the last bit; matching nudges the
pixel up or down by one so it is harder to detect; 2-LSB uses two bits per pixel and holds twice as much. The
**mode** is *keyed* or *sequential*. Keyed means the positions are scattered by a secret key, so without the key
you cannot even find where the message is. Sequential writes in order from the top, which is simple but easy to
spot."

### Step 4 (Result) and press Hide message

**ON SCREEN:** the result appears. Work down it slowly.

1. **Before / after slider and the difference map.**
   "Drag the slider. The two pictures look identical. Now the difference map, amplified fifty times: every white
   dot is one pixel that changed, by exactly one brightness level. In keyed mode the dots are spread evenly
   across the whole picture. In sequential mode they would all be in the top rows."
2. **Quality numbers: PSNR, SSIM, changed pixels.**
   "PSNR and SSIM are standard image-quality measures, higher is better. The page itself says that above about 40 dB the
   difference is invisible to the eye; read your actual number off the screen (it is higher for a short message
   and lower for the long one). SSIM close to 1 means the structure is the same.
   **[MULTIMEDIA]** These are the same measures used to judge image compression."
3. **"Prove the message is hidden" panel.** This is the part that convinces a sceptical audience. Say:
   "You are probably thinking: the pictures look the same, how do we know anything is in there? Three pieces of
   evidence."
   - **1. The pixels are different.** "Two fingerprints, SHA-256 hashes of the pixel data. A hash changes
     completely if even one pixel changes. These two are different, so the image really was altered. The second
     fingerprint is the one the sender signs."
   - **2. The pixel values that changed.** "This is an eight-by-eight patch cut from the picture where the
     message left the most changes. Left, the original. Right, the stego image, with the changed cells
     highlighted. Read one pair aloud, for example 'one hundred eighty-two became one hundred eighty-three'.
     In binary, only the last digit differs. *(The page explains this sentence automatically for whichever
     method you chose; for matching it says the pixel moved by one so that it is odd or even as needed.)*"
   - **3. Read the message back.** "Press **Read the message back**. This sends the exact file you could
     download, the same bytes, through the receiver. All six stages pass and the original text comes back.
     Now press **Try a wrong password**. Nothing comes back, and the page says why. With a wrong password the
     receiver cannot even find where the message is hidden."
4. **Downloads.** "The stego PNG, the signed manifest, and the public key. Two safety notes the page shows: the
   picture is served as exact bytes, never re-drawn on a canvas, because re-saving would destroy the hidden
   bits. And keep the manifest separate from the image: it proves integrity but also reveals that a hidden
   payload exists."

**Handoff within Person 1:** "The picture goes to the receiver. Let us be the receiver." Click **Extract &
verify**.

---

# Part 3. Extract and verify: the receiver (Person 1, 2 minutes)

**ON SCREEN:** Extract page. Click **Load the image from the Hide step** (violet, presenter mode). The image, the
public key, the password and the manifest fill in. Point out how few boxes there are.

**SAY:**
> A real receiver would be given three things: the picture, the sender's public key, and the password. That is
> all. Notice what is **not** here: nothing asks how the message was hidden. The server works that out from the
> picture itself, by trying the possible layouts and checking a built-in checksum. A wrong guess fails the
> checksum, so it is unambiguous.

Press **Extract and verify**. The result scrolls into view.

**WHAT THE OUTPUT MEANS (success):**
- **The verdict card, "Message verified".** "The sender's signature is valid, so the message is genuine."
  Open **Details** to show the key fingerprint and which layout and technique were found.
- **"What the receiver checked": six stages.** Read them aloud briefly: *read image, extract hidden bits,
  parse packet, check sender fingerprint, verify the Ed25519 signature, derive the key and decrypt.* "Look at
  the order. The signature is checked at stage five. The password is only used at stage six. **A forged or
  altered package is rejected before any decryption is attempted.** That is the single most important security
  idea on this page **[INFO SECURITY] [CRYPTOGRAPHY]**."
- **The message,** with its length and Copy and Download buttons.
- **"Is the image exactly what the sender made?" (three manifest checks).**
  "These use the separate signed manifest. First: no pixel changed since signing. Second: the sender signed
  these details. Third: the sender signed the hidden message. The first one fails if even *one* pixel changed,
  even when the message can still be read."

**Now show failure (this is what impresses examiners).** Change the password to anything wrong, press **Extract
and verify** again.

**WHAT THE OUTPUT MEANS (failure):** "'No hidden message found.' It says either there is no message for this
password, or the password is wrong, and that the two look the same **on purpose**. If an attacker could tell
the difference, they could test passwords against the picture. Look at the stages: stage two fails, stages
three to six are *skipped*. Nothing was decrypted and no partial text is ever shown."

*(Other failure messages you can mention, but need not demo: "Signed by someone else" if the public key is
wrong; "The signature does not match" if the picture was changed; "A message was found but it is damaged" if
it was resized or saved as JPEG.)*

**Handoff:** "That is the crypto side of the project. Now my teammate will show the defender's side." Hand over.

---

# Part 4. How it works (Person 1, 30 seconds; optional if time is short)

**ON SCREEN:** **How it works** page. Show the packet table.

**SAY:**
> The whole message travels as one packet. 128 bytes of overhead around your text: a magic number and version,
> the sender's key fingerprint, a random salt and nonce, the ciphertext, and a 64-byte **Ed25519 signature over
> everything before it**. You may ask: AES-GCM already protects integrity, so why sign? GCM only protects
> against people who do *not* know the password. It cannot prove *who* sent it, and a signature lets the
> receiver throw out a forged package cheaply, before running the expensive Argon2id step.
>
> One more term: **bpp, bits per pixel**: how many message bits per pixel. 1.0 means every pixel's last bit is
> used; 0.05 means one in twenty. Remember this number. It decides whether the next section works.

**Handoff to Person 2.**

---

# Part 5. The detector (Person 2, 6.5 minutes)

## 5a. Detect hidden data (3 minutes)

**ON SCREEN:** click **Detect** in the top bar. Presenter mode shows two violet buttons.

**SAY (opening):**
> Now we change sides. I am the defender. I am handed a picture and have to decide if it is hiding something.
> **[AI]** I have three detectors, and they are very different.
>
> 1. **Statistical tests.** Old-school mathematics, not trained. They look for the exact pattern that overwriting
>    the last bit leaves in pixel values: chi-square, RS analysis, sample-pair analysis. Transparent, but blunt.
> 2. **A feature-based classifier.** A trained machine-learning model. We compute 1,068 measurements from each
>    image and a gradient-boosting model learned, from thousands of examples, which combinations mean
>    "hidden".
> 3. **A neural network.** A small convolutional network of about 111,000 trainable numbers. A fixed filter first
>    removes the picture's content, leaving only the faint noise, because the network should study the noise
>    and not the cat in the photo.
>
> The final verdict combines the two trained detectors, with weights chosen on separate validation data.

**Step A: scan the clean cover.** Click **Load the demo cover**, then **Scan image**.

**WHAT THE OUTPUT MEANS (clean image):**
- **Badge "Not flagged".**
- **Likelihood score** (for the demo cover, a few percent) with a bar and a **vertical marker**. "The marker is the
  flagging line. Below it, not flagged."
- **Three small cards:** each detector, its own status and bar. "They can disagree, and when they do, that is
  informative."
- **Short sentence under the verdict:** "Nothing unusual was found. This does not prove the image is clean: a
  short message changes too few pixels to notice."

**Step B: scan the image that holds a message.** Say: "A moment ago my teammate hid a message. Let us scan that
image." (For this to be convincing, **Person 1 should have used 'Same, with a longer message' on the Hide
page**, and you load it with **Load the stego image from Hide**.) Press **Scan image**.

**WHAT THE OUTPUT MEANS (stego image):**
- **Badge "Hidden data suspected"** and a score near the top of the bar, past the marker.
- **A "Try to read it in Extract & verify" button.** "A defender who flags an image can go on to try reading it,
  if they had the key. They usually do not."
- **"Where the detector looked."** Toggle **Network attention** and **Fine-grain noise** and move the opacity
  slider. "A heat map: where the network responded most strongly. It is a hint, not proof, and the page says
  so."
- **Open "Technical details".** "For people who want the raw numbers: each detector's score and threshold,
  which model produced it, and the measurements table with the names of the classical tests."
- **Open "Look at the lowest bit layer"** (below the result). "The same bit-plane idea as the Home animation, now
  on this image. Where the message was written, the layer turns to noise."

**Be honest about the short-message demo, out loud:**
> We also hid a one-sentence message earlier. It did **not** get flagged. A short message changes only a
> handful of pixels. That is a real limitation, not a bug, and it is exactly why we say "not flagged" and not
> "clean". We measured it: a message of about a thousand characters is flagged reliably, a 200-character one is
> not.

**Show Sensitivity:** "Balanced gives the best overall accuracy. 'Fewer false alarms' flags only when quite
sure. It is the trade-off every security alarm has."

## 5b. Compare detectors: the arms race (1.5 minutes)

**ON SCREEN:** **Compare detectors**. Press **Load the demo cover** (violet, presenter mode). Choose **LSB matching**,
**Keyed**, set the payload slider to **0.1 bpp**, press **Embed and scan**.

**SAY:**
> This page lets you play the attacker and the defender at the same time. Choose a hiding method and how much
> to hide, in bits per pixel. The page hides a random message with a throw-away key and then scores both the
> clean image and the modified image with every detector.

**WHAT THE OUTPUT MEANS:** the table has two columns, **Original** and **With message**, and a last row with the
final verdict ("Not flagged" or "Hidden data suspected"). "A good detector has a big gap between the two. Where
the two scores are close, the hiding wins." Above the table, **PSNR**, **SSIM**, **actual payload** and **samples
changed** describe the hiding itself. In our rehearsal (LSB matching, 0.1 bpp, keyed): PSNR 61.1 dB, 5.06% of
samples changed, the untrained statistical tests scored the modified image only 0.075 while the two trained
detectors scored 0.98 and 1.00. Say it plainly: the old tests miss it, the trained ones do not. The slider's own
hint explains bpp. Then slide the payload up and
rerun, and contrast **LSB replacement** with **LSB matching**.

Read the two callouts at the bottom of the page:
- **Why low payloads are hard:** "At 0.05 bits per pixel, only five percent of pixels carry a bit, and about half
  of those already match, so the statistics barely move."
- **Why LSB matching is harder:** "Replacement only ever swaps a pixel between a pair of values, 2k and 2k+1.
  The classic tests exploit that. Matching moves by plus or minus one, which crosses those pairs and removes
  the pattern they rely on."

**Real numbers you can quote (from our held-out test images, BOSSbase 1.01, 1,500 test images, 256 by 256
grayscale, seed 1337).** Choose two or three:
- For ordinary LSB replacement at 0.4 bpp the combined detector scores an area under the ROC curve of about
  **0.997**, nearly perfect.
- For LSB matching at 0.05 bpp it drops to about **0.82**, and the untrained statistical tests are at chance,
  about 0.53.
- The neural network is clearly better than the old tests exactly where hiding is hardest, for example about
  **0.96** at 0.1 bpp matching, against about **0.78** for the feature classifier.
- We tested on three techniques the detectors were **never trained on** (2-LSB, and simulations of S-UNIWARD and
  HILL) and report those rows separately. We do not claim the detectors are good at them.
- **Live demo of exactly that:** on this page choose **S-UNIWARD (STC)** (or HILL), payload **0.4 bpp**, press
  **Embed and scan**. Expected, and rehearsed: PSNR about 58 dB, about 9.6% of samples changed (plain LSB at
  the same payload changes about 20%), and **"Not flagged"** in the With-message column; the neural network scores
  about 0.00. Then switch to **LSB matching** at 0.4 bpp: it is flagged. Say it honestly: "A smarter hiding
  method hides in the busy parts of the picture, and our detectors, which learned from plain LSB hiding,
  do not catch it. On three test covers at 0.4 bpp, LSB matching was flagged 3 of 3 and S-UNIWARD and HILL
  0 of 6. That is three images, an example and not a benchmark. It is the arms race in one slide, and it is
  our main piece of future work." The page shows the same warning.

*(AUC in one sentence: "1.0 is a perfect detector, 0.5 is a coin toss.")*

## 5c. Batch scan and the model story (1 minute)

**ON SCREEN:** **Batch scan**.

**SAY:** "Real defenders do not scan one picture. Here you add up to twenty images at once, press **Scan all**,
and get a table you can sort and filter and export to a spreadsheet file. Click any row to open the full
breakdown we just saw. A bad file in the batch gives its own error and does not stop the others."

**WHAT THE OUTPUT MEANS:** each row shows the image, a verdict ("Not flagged" or "Suspected"), a **score**, and
which detector scored highest, by its plain name. Under the table: "Images scoring 69.3% or more are flagged."
Press **Open** on a row: the full breakdown from the Detect page opens below and the page scrolls to it. A file
that is not an image (try a text file) is refused with a clear message before any scanning, and the other
images still scan. *(Rehearse once with three images and one text file.)*

**SAY (how the models were built, in four sentences):**
> The data is BOSSbase, a standard research set of ten thousand photographs, split into 7,000 for training and
> 1,500 each for validation and testing, with no image shared between the groups. We embedded messages with our
> own sender code at several payload levels, so every training example is a real, recoverable stego image. The
> neural network trained for about an hour and a half on a graphics card. And the thresholds and the combination
> weights were chosen on validation data only, never on the test images.

**Handoff to Person 3:** "So the defender can catch heavy hiding but struggles with light hiding. What if an
attacker does not just look, but changes the picture? Over to you."

---

# Part 6. The proof: security and engineering (Person 3, 6 minutes)

## 6a. Tamper test (2 minutes)

**ON SCREEN:** **Tamper test**. In presenter mode press **Load the image from the Hide step**; nothing else needs
entering, and there is no mode to choose, because the receiver works out how the message was hidden from the
image itself (this includes S-UNIWARD and HILL images). Pick an
attack. Start with **No attack (control)**, press **Apply attack and verify**. The result card at the top gives
one plain headline, and the page scrolls to it. **A nice contrast if you have a minute:** hide a message with
**S-UNIWARD (STC)** on the Hide page, then run **Flip 1 pixel LSB** here. With plain LSB the message survives (amber
headline); with S-UNIWARD the **signature check fails every time** (we ran it 4 times), because every pixel
takes part in decoding. Either way the change is caught.

**SAY:**
> This is the page where we try to break our own system **[INFO SECURITY]**. It takes the verified stego image,
> damages it **in your browser**, then sends the damaged file to the receiver and shows which checks fail.

**WHAT THE OUTPUT MEANS:**
- **Control (no attack):** the headline reads "The message is intact" and every check passes. "This proves the
  test itself is fair."
- **Flip 1 pixel LSB:** the headline reads **"The message survived, but the image was altered"** (amber). "We
  change a single pixel by one. All six receiver stages still pass, so the message is readable, but the first
  check under *Is the image exactly what the sender made?*, **No pixel was changed since signing**, fails,
  because the manifest says exactly what the image should be. The point: even a change nobody could ever see
  is *detected*."
- **JPEG re-compress** (a lossy attack): "Now we save the picture as a JPEG, like a messaging app would. The
  hidden bits are destroyed." The headline reads **"No hidden message found"** (red) and stages three to six are
  skipped. This is the main weakness of
  hiding in the last bit: it does not survive compression or resizing **[MULTIMEDIA]**.
- Mention the others by name (flip many bits, add plus-or-minus-one noise, crop 8 pixels, resize to 50%) and
  summarise: "The hiding is fragile on purpose, because it lives in the last bit. The signatures do not make it
  strong, they make every damage **visible**: you always know when something was altered."

*(Rehearse each attack once and note what the page says, so you are not surprised. The page's own description
under each attack is a good thing to read aloud.)*

## 6b. Architecture and security rules (2 minutes)

**ON SCREEN:** slide with the architecture diagram (from `docs/ARCHITECTURE.md`) or the **How it works** page.

**SAY:**
> Three layers. A **React website** with TypeScript, which has no business logic. A **thin FastAPI layer** that
> only validates uploads, calls the core, and turns errors into clean messages. And two **pure-Python cores**,
> one for crypto and hiding, one for detection, that never import the web framework. That rule means the core
> is tested without a server, and every function can be explained on its own.

Then the security rules, one short sentence each. Choose all of them if time allows:
1. **Verify before decrypt** (already shown).
2. **No keys, passwords or messages in logs or files.** The server is **stateless**: uploads live only in
   memory, nothing is written to disk.
3. **Constant-time comparisons** for secrets, and a **unique salt and nonce for every message**.
4. **Positions are reproducible by the receiver** because they come from a ChaCha20 keystream, never an ordinary
   random-number generator, which could differ between machines.
5. **Uploads are checked by actually decoding them**, with size and pixel limits and a rate limit on every POST
   endpoint (30 per minute).
6. **The stego image is served as exact bytes.** If the browser redrew it on a canvas to download, the hidden
   bits would be silently rewritten.

**Testing, with real numbers:** "The backend has **240 automated tests passing**, none skipped (they include real S-UNIWARD and HILL round trips), with **91% coverage of the crypto and hiding core**. The website has **58 tests**,
including automatic accessibility checks. There is also an **18-step smoke test** that exercises the real running
server end to end, including a wrong password and an uploaded JPEG being refused." *(If the numbers change before
the talk, rerun the tests and quote the new ones.)*

## 6c. Honest limits, ethics, and the About page (1.5 minutes)

**ON SCREEN:** **About** page. Scroll through its sections.

**SAY (be direct, this earns trust):**
> What this is **not**:
> - Not a secure messenger for real secrets. It is a demonstration, and Python cannot promise to wipe secrets from
>   memory.
> - Hiding in the last bit does **not** survive JPEG, resizing, or screenshots.
> - The detectors are statistical. They produce false alarms and misses, and a high score is a reason to look
>   closer, **not proof**.
> - Light hiding, with few changed pixels, can slip past the detectors. We showed that ourselves.
> - The two advanced methods, S-UNIWARD and HILL, carry real messages here, but they need an optional compiled
>   package, which is installed on our machine but not required elsewhere. Our *stored* detector results for them
>   come from a *simulation* of where those schemes would change pixels, not from real messages, and we say so
>   in the documentation. We have only seen the detectors on real S-UNIWARD and HILL messages in a live demo on
>   three covers, where they were not flagged; a proper measurement is a separate experiment we have **not** run.
>
> **Ethics.** Steganography is dual-use: it protects journalists and dissidents, and it can hide wrongdoing. We
> wrote an acceptable-use statement, we use throw-away demo keys, we never touch anyone else's images, and
> detection is part of the project exactly because defenders need these tools too.
>
> **Privacy.** Nothing you upload is stored. Everything is processed in memory and discarded.

---

# Part 7. Close (Person 3, then all three stand, 1 minute)

**SAY (Person 3):**
> To summarise, in the same three words we started with. **Cryptography:** the message is encrypted with
> Argon2id and AES-256-GCM, signed with Ed25519, and the receiver verifies before it ever decrypts.
> **Information security:** every failure is visible and explained, tampering is caught, the server keeps
> nothing, and we are honest about what the system cannot do. **Artificial intelligence:** three detectors, two of
> them trained, which can flag heavy hiding almost perfectly and show exactly where light hiding becomes hard.
> All of it on **images**, for the **multimedia** domain, in one working website you have just seen.

**Person 1:** "Thank you." **Person 2:** "We are happy to take questions."

---

# Questions: who answers what

Open `docs/VIVA_QA.md` for the full list of 45. These are the likeliest, with a one-line answer and an owner.

| Likely question | Owner | One-line answer |
|---|---|---|
| Why sign *and* encrypt? | Person 1 | GCM protects against people without the password; the signature proves who sent it and lets us reject forgeries before the expensive key derivation. |
| Why Argon2id? | Person 1 | It is memory-hard (64 MiB), so password guessing is expensive even on GPUs. |
| Why verify before decrypt? | Person 1 | A forged package must never reach the decryption code; it fails cheaply and leaks nothing. |
| Why does the wrong password look like "no message"? | Person 1 | On purpose: if the two cases differed, an attacker could test passwords against the picture. |
| What is keyed scatter? | Person 1 | A ChaCha20-derived secret permutation picks which pixels carry bits, so without the key you cannot find them. |
| How did you train the models, and on what? | Person 2 | BOSSbase 1.01, 10,000 photos, 7,000 / 1,500 / 1,500 split, no image shared across splits, messages made by our own sender code, fixed seed. |
| How do you know it is not overfitted? | Person 2 | Cover-disjoint held-out test images, thresholds fixed on validation only, and separate rows for techniques never seen in training. |
| Why is LSB matching harder to detect? | Person 2 | Plus-or-minus-one steps cross the 2k/2k+1 pairs that chi-square, RS and SPA rely on. |
| What do the scores mean? | Person 2 | The likelihood score is a model output in 0 to 1, flagged at a threshold chosen on validation; it is evidence, not proof or a literal probability. |
| What is AUC? | Person 2 | 1.0 is perfect, 0.5 is a coin toss; it measures how well the detector ranks stego above clean at every threshold. |
| Can it survive JPEG or WhatsApp? | Person 3 | No. Last-bit hiding needs lossless files; the Tamper test demonstrates exactly this. |
| Is it a real secure messenger? | Person 3 | No. It is a demonstration; see About and the threat model. |
| What stops abuse of the server? | Person 3 | Size and pixel limits, decoding to validate, rate limiting, no storage, uniform error messages. |
| Why does the server store nothing? | Person 3 | Less to leak: no uploads, messages or keys ever touch disk or logs. |
| How do you know the numbers are real? | Person 3 | Every metric is generated by a script into `metrics.json` and the model card; the website and docs never hard-code results. |
| What about S-UNIWARD and HILL? | Person 2 | Cost maps are implemented; stored detector results for them come from a simulator that carries no message; the real embedder works here (it needs an optional compiled package) and on 3 covers at 0.4 bpp the detectors did not flag it, but that is not a measured benchmark. |

---

# If something goes wrong (Person 3)

| Problem | What to do and say |
|---|---|
| **Red "backend offline" badge** | Start the backend (`uvicorn app.main:app --port 8000` in `backend/`, or `scripts/start_app.ps1`). The page recovers on the next request. Say: "The server restarted; nothing is stored, so nothing is lost." |
| **Page reloaded and demo keys vanished** | Go to Hide, click **Fill demo cover, message and keys**, press Hide again. It takes 10 seconds. |
| **429 "too many requests"** | Wait the number of seconds shown, or restart the backend. Say: "That is our rate limiter working." |
| **Stego image is not flagged on Detect** | Use the **longer message** button on Hide, which is built for this. Or say the honest line about short messages. |
| **First request is slow** | Argon2id deliberately takes a moment (64 MiB). Say so; it is the point. |
| **A page throws an error** | The app shows "This view hit an unexpected error" with a **Try again** button. Click it. Otherwise move on and describe the page from this script. |
| **Examiner asks to try a different image** | Allowed: use a PNG, at least 256 by 256 pixels. Warn that a JPEG-origin photo can confuse the detectors and a JPEG file cannot carry a message. |

Never demo with real secrets. All passwords in presenter mode are fixed public demo strings.
