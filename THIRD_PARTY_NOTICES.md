# Third-party notices

BookMatch’s application code is currently unlicensed. These notices describe separate dependencies and data sources; they do not assign a license to BookMatch.

| Component | Use | Upstream terms |
| --- | --- | --- |
| PySide6 / Qt for Python, Shiboken6 | Desktop interface and Python bindings | LGPLv3 / GPL alternatives in the installed distributions; [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html) |
| FastEmbed | Local embedding model loader | [Apache License 2.0](https://github.com/qdrant/fastembed/blob/main/LICENSE) |
| BAAI `bge-small-en-v1.5` | Optional downloaded embedding model | [MIT, as stated by its model card](https://huggingface.co/BAAI/bge-small-en-v1.5) |
| ONNX Runtime | Local model execution | [MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE) |
| PyInstaller | Build tool | [GPL with its distribution exception](https://pyinstaller.org/en/stable/license.html) |
| Open Library / Internet Archive | Public catalog metadata, aggregate counts, optional covers and work lookups | [Open Library licensing statement](https://openlibrary.org/developers/licensing) and [catalog provenance](data/SOURCE.md) |

Dependency packages contain additional components with their own notices. The reviewed Mac dependency set is recorded in `requirements-lock-macos-arm64.txt`; Windows dependencies must be reviewed on Windows. Packaging includes Qt/PySide/Shiboken distribution metadata, the upstream LGPLv3 and GPLv3 texts in `third_party/licenses`, and the FastEmbed and ONNX Runtime files collected by their packaging options. The PySide wheels used for this Mac build do not themselves contain those full Qt license texts.

Open Library does not assert new copyright over its database and notes that existing rights may apply to contributions. The source repository bundles a compact selection of bibliographic metadata and aggregate reading-log counts with attribution. It bundles no reader records, descriptions, cover artwork, model weights, or private libraries. Covers and descriptions are retrieved locally from their public sources as described in the provenance document; this project does not claim ownership of them.

Before distributing public app binaries, verify the licenses and included notices for the exact packaged dependencies, including the relevant Qt modules and their upstream components. Source publication and binary distribution are separate release steps.
