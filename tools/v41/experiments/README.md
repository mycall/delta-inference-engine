# RTX Spark allocation experiment

`spark-allocation-retry.patch` retains the unselected CUDA staging/MMQ allocation
retry and its reduced-arena test option. SHA256:
`63820d4de8d1de807d8fda9fa4dd9eee719ebfab9c6d7d7f2ed9334e2c9c22d7`.

It is an experiment, not part of the selected engine or default source. Its
serving comparison did not establish a useful speed gain or exercise the
fallback in serving; a chunk comparison also found numerical differences.
The earlier candidate crash coincided with Windows commit pressure.

The local operating solution keeps the original engine and uses the tested
RTX Spark profile with the user-configured 128/160-GiB pagefile. Controlled
requests and contained OpenCode trials completed without engine replacement.
The retry candidate is not needed to run that setup.

For further work, apply this patch only in an isolated checkout, compile a
separate executable, and repeat the relevant numerical and serving checks.
Do not overwrite the selected executable. The integration repository's
`history/2026-11-14-ds41-mmq-allocation.md` and
`history/2026-11-14-system-commit.md` retain the measurements and failures.
