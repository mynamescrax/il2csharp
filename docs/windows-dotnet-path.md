# Keep temporary .NET tool directories out of the Windows PATH

Set `DOTNET_ADD_GLOBAL_TOOLS_TO_PATH=false` **before launching the .NET CLI** when using a disposable `DOTNET_CLI_HOME`. Otherwise, first-run setup can append `<temporary home>\.dotnet\tools` to the persistent user `Path`. Deleting the temporary directory does not remove that entry.

This project encountered a user `Path` with hundreds of temporary entries. The `.dotnet\tools` suffix and fresh pytest homes were consistent with SDK first-run setup; the entries alone did not identify which process wrote them. A long saved `Path` can break command lookup in `cmd.exe` even when launching an executable by its full path works.

## Set the Windows default

In **PowerShell as Administrator**, set the machine environment variable:

```powershell
$name = 'DOTNET_ADD_GLOBAL_TOOLS_TO_PATH'
[Environment]::SetEnvironmentVariable($name, 'false', 'Machine')
[Environment]::GetEnvironmentVariable($name, 'Machine')  # expected: false
```

For an account with an overriding user value, run `[Environment]::SetEnvironmentVariable($name, 'false', 'User')` as that user. To protect the current PowerShell session immediately, run `$env:DOTNET_ADD_GLOBAL_TOOLS_TO_PATH = 'false'`. Restart long-running terminals, IDEs and build agents to pick up the saved setting; signing out and back in refreshes the whole user session.

This disables the SDK's automatic tools-directory addition. It does not remove existing entries, stop other software from editing `Path`, or prevent a launcher from explicitly overriding the setting. If you use global .NET tools, keep their actual, stable tools directory on `Path`.

## Verify with one small test

`tests/dotnet_case.py` sets the variable explicitly in the child environment for **both** `dotnet --version` and `dotnet run`, so tests also work safely on machines without the Windows default. `DOTNET_SKIP_FIRST_TIME_EXPERIENCE` is not a substitute for this opt-out.

From the repo root on Windows with a .NET 8+ SDK:

```powershell
python -m pytest -q -rs tests/test_dotnet_path.py
```

Look for `1 passed`. The test starts with a fresh CLI home, checks the environment before each launch, and builds and runs a tiny program. It compares the **unexpanded value and registry type** of `HKCU\Environment\Path` before and after, without printing or rewriting the user's paths. A skip means the SDK check did not run.

Verification on the affected Windows PC: `1 passed`; the saved user `Path` value and its registry type were identical before and after the fresh-home run.

References: [Microsoft's .NET CLI environment variables](https://learn.microsoft.com/dotnet/core/tools/dotnet-environment-variables#dotnet_add_global_tools_to_path) and [Command Prompt command-line and environment limits](https://learn.microsoft.com/troubleshoot/windows-client/shell-experience/command-line-string-limitation).
