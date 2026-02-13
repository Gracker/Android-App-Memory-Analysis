#!/usr/bin/env python3

import subprocess


def run_adb_command(adb_path, arguments, timeout=30):
    try:
        result = subprocess.run(
            [adb_path, *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = result.stdout if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""
        return stdout, result.returncode, stderr
    except subprocess.TimeoutExpired:
        return "", -1, f"timeout ({timeout}s)"
    except Exception as error:
        return "", -1, str(error)


def run_adb_shell(adb_path, command, timeout=30):
    return run_adb_command(adb_path, ['shell', command], timeout)


def read_first_successful_shell_output(adb_path, commands, timeout=60):
    last_error = ""
    for command in commands:
        output, return_code, stderr = run_adb_shell(adb_path, command, timeout)
        if return_code == 0 and output.strip():
            return output, ""
        if stderr:
            last_error = stderr
        elif output.strip():
            last_error = output.strip()
    return "", last_error


def smaps_shell_commands(pid):
    return [
        f'cat /proc/{pid}/smaps',
        f'su -c "cat /proc/{pid}/smaps"',
        f'su 0 cat /proc/{pid}/smaps',
    ]


def read_smaps_with_shell(shell_executor, pid, timeout=60):
    last_error = ""
    for command in smaps_shell_commands(pid):
        output, return_code = shell_executor(command, timeout)
        if return_code == 0 and output.strip():
            return output, ""
        if output.strip():
            last_error = output.strip()
    return "", last_error


def read_smaps_with_adb(adb_path, pid, timeout=60):
    return read_first_successful_shell_output(adb_path, smaps_shell_commands(pid), timeout)


def dmabuf_shell_commands():
    return [
        'cat /sys/kernel/debug/dma_buf/bufinfo',
        'su -c "cat /sys/kernel/debug/dma_buf/bufinfo"',
        'su 0 cat /sys/kernel/debug/dma_buf/bufinfo',
    ]


def read_dmabuf_with_adb(adb_path, timeout=60):
    return read_first_successful_shell_output(adb_path, dmabuf_shell_commands(), timeout)


def parse_ps_processes(ps_output):
    processes = []
    for raw_line in ps_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        process_name = parts[-1]
        if process_name in ("NAME", "CMD", "COMMAND"):
            continue
        pid = None
        for token in parts[1:-1]:
            if token.isdigit():
                pid = int(token)
                break
        if pid is None:
            continue
        processes.append((pid, parts[0], process_name))
    return processes


def list_processes_with_adb(adb_path):
    for command in ('ps -A', 'ps'):
        output, return_code, _ = run_adb_shell(adb_path, command, timeout=30)
        if return_code != 0 or not output.strip():
            continue
        return parse_ps_processes(output)
    return []


def resolve_pid_with_shell(shell_executor, package_name):
    for command in (f'pidof {package_name}', f'pidof -s {package_name}'):
        output, return_code = shell_executor(command, 20)
        if return_code == 0 and output.strip():
            for token in output.split():
                if token.isdigit():
                    return int(token)

    for command in ('ps -A', 'ps'):
        output, return_code = shell_executor(command, 30)
        if return_code != 0 or not output.strip():
            continue
        for pid, _, process_name in parse_ps_processes(output):
            if process_name == package_name or process_name.startswith(f"{package_name}:"):
                return pid

    return None


def resolve_pid_with_adb(adb_path, package_name):
    def shell_executor(command, timeout):
        output, return_code, _ = run_adb_shell(adb_path, command, timeout)
        return output, return_code

    return resolve_pid_with_shell(shell_executor, package_name)
