# Notice

`CASE-STUDY.md` in this directory quotes short excerpts (file paths, line numbers, struct/function
names, and short paraphrased descriptions of a real diff) from a local clone of
[BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep), tag `15.2.0`, commit
`e89fff89ac9af12e8d4ce9d5fd07beb408ca730f`. No `graphify-out/` artifacts, and no ripgrep source
files, are vendored into this directory.

ripgrep is dual-licensed under the Unlicense and the MIT License. The MIT License text:

```
The MIT License (MIT)

Copyright (c) 2015 Andrew Gallant

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

This attribution is included per the license's own terms; it does not extend or alter this
repository's own Apache-2.0 license, which governs everything else in `context-engineering-oss`.

The specific bug fix this case study examines — PR
[#3100](https://github.com/BurntSushi/ripgrep/pull/3100), "printer: preserve line terminator when
using `--crlf` and `--replace`" (merge commit `64174b8e68b59e560ad459f3c11cc9c4f00964bd`) — was
authored by IsaacOscar and merged by Andrew Gallant (BurntSushi); this case study only describes and
quotes short excerpts of that change, it does not claim authorship of it.
