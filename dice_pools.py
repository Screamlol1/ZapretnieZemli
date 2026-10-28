"""Table rule: penalties roll alongside the full skill pool, cancelling successes."""

def skill_counts(skill, *modifiers):
    return skill + sum(max(0, m) for m in modifiers), sum(max(0, -m) for m in modifiers)

def result_text(positive, penalty):
    return f'Успехов: {positive} − {penalty} = {max(0, positive-penalty)}.' if penalty else f'Успехов: {positive}.'
