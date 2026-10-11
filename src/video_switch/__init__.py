"""Video Switch desktop application."""


def main() -> None:
    """Start the desktop application."""
    from video_switch.app import main as run

    run()


__all__ = ["main"]
