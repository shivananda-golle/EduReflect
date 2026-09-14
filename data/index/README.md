# Knowledge-base index

- `faiss.index`: 2,316 passage vectors (384-dim, cosine similarity) from `BAAI/bge-small-en-v1.5`
- `metadata.json`: passage text and source file for each vector, in index order

Rebuild with `python -m app.services.kb_builder --from-metadata` (same passages) or from `data/clean/` (new content).

## Sources

- **NCERT textbooks** (1,207 passages): Class 9 Mathematics (`iemh1*`) and Class 10 Science (`jesc1*`), © National Council of Educational Research and Training, freely available at <https://ncert.nic.in/textbook.php>. Excerpts are included for non-commercial educational use only.
- **Wikipedia** (1,109 passages): articles on core science topics, licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Text was extracted and split into chunks.
