import subprocess


def run(command):
    return subprocess.call(command, shell=True)
