from __future__ import annotations

import subprocess


def notify(title: str, message: str) -> bool:
    """Best-effort local Windows toast; the application status remains authoritative."""
    safe_title = title.replace("'", "''")
    safe_message = message.replace("'", "''")
    script = (
        "$template=[Windows.UI.Notifications.ToastTemplateType]::ToastText02;"
        "$xml=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template);"
        f"$xml.GetElementsByTagName('text')[0].AppendChild($xml.CreateTextNode('{safe_title}'))|Out-Null;"
        f"$xml.GetElementsByTagName('text')[1].AppendChild($xml.CreateTextNode('{safe_message}'))|Out-Null;"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('CDD Review Workflow').Show($toast)"
    )
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
