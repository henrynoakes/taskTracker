from datetime import date


def format_schedule_date(scheduled_date: date, today: date) -> str:
    days_away = (scheduled_date - today).days
    if days_away == 0:
        return "Today"
    if days_away == 1:
        return "Tomorrow"
    if 2 <= days_away <= 6:
        return scheduled_date.strftime("%A")

    full_date = f"{scheduled_date.strftime('%A')}, {scheduled_date.day} {scheduled_date.strftime('%B')}"
    if scheduled_date.year != today.year:
        full_date += f" {scheduled_date.year}"
    return f"Overdue — {full_date}" if days_away < 0 else full_date


def format_duration(increments: int) -> str:
    hours, minutes = divmod(increments * 30, 60)
    parts = []
    if hours:
        parts.append(f"{hours} h")
    if minutes or not hours:
        parts.append(f"{minutes} min")
    return " ".join(parts)
