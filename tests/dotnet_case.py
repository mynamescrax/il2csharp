"""Build and run a local regression program with no package feeds."""
import os
import re
import shutil
import subprocess

import pytest


def run_case(root, runner, references=()):
    dotnet = shutil.which('dotnet')
    if not dotnet:
        pytest.skip('behavior check requires a .NET 8+ SDK')
    env = dict(os.environ, DOTNET_CLI_HOME=str(root / 'home'), DOTNET_NOLOGO='1',
               DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
    version = subprocess.run([dotnet, '--version'], cwd=root, env=env, text=True,
                             capture_output=True, timeout=30)
    match = re.search(r'^(\d+)\.\d+\.\d+', version.stdout, re.M)
    if not match or int(match[1]) < 8:
        pytest.skip('behavior check requires a .NET 8+ SDK')

    project = runner / 'Verify.csproj'
    refs = ''.join('<ProjectReference Include="%s" />' % path for path in references)
    project.write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
        f'<TargetFramework>net{match[1]}.0</TargetFramework>'
        '<CheckForOverflowUnderflow>true</CheckForOverflowUnderflow>'
        f'</PropertyGroup><ItemGroup>{refs}</ItemGroup></Project>', encoding='utf-8')
    (root / 'NuGet.Config').write_text(
        '<configuration><packageSources><clear /></packageSources></configuration>',
        encoding='utf-8')
    run = subprocess.run([dotnet, 'run', '--project', str(project)], cwd=root,
                         env=env, text=True, capture_output=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout
