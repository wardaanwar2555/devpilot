def close(handle):
    try:
        handle.close()
    except OSError:
        pass
