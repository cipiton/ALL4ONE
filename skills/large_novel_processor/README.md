# Large Novel Processor

`Large Novel Processor` is a reusable preparation skill for oversized novel `.txt` files.

It detects chapter headings, then writes either:

- one file per chapter under `chapters/`
- grouped chapter bundles under `chunks/`

Every run also writes `index.txt` into the normal shared output folder.

Run it from the shared terminal flow:

```bash
python run.py
```

Then choose `Large Novel Processor`, select a `.txt` novel file, choose `chapter` or `chunk`, and if needed provide a chunk size.

Use the resulting output folder as the prepared source for downstream skills when the original novel is too large to send directly to the model.
