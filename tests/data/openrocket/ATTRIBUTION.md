# OpenRocket sample files

`v2412/`, `v2309/`, `master/` contain the example and test `.ork` files shipped in the OpenRocket repository
(https://github.com/openrocket/openrocket, tags `release-24.12`, `release-23.09`, and `master` as of 2026-10-03),
licensed GPL-3.0. File names are `<source directory path with / replaced by _>__<original name>.ork`.
They are used only as test fixtures and are not distributed with the application.

`synthetic/` holds generated files (`tools/oracle/gen_synthetic.py`) that exercise shapes and features the
official samples do not cover.

`expected/` holds reference values produced by OpenRocket 24.12 itself (`tools/oracle/run_oracle.py`).
