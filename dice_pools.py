"""Table rule: penalties roll alongside the full skill pool, cancelling successes."""

def artifact_sides(data):
    """Mixed D8/D10/D12 pools; accept the legacy single-die request too."""
    if 'artifacts' in data:
        values=data['artifacts']
        if not isinstance(values,list) or len(values)>10 or any(type(v)!=int or v not in (8,10,12) for v in values):
            raise ValueError('Артефакты: до 10 костей D8, D10 или D12 суммарно.')
        return list(values)
    value=data.get('artifact',0)
    if type(value)!=int or value not in (0,8,10,12):raise ValueError('Артефакт: D8, D10 или D12.')
    return [value] if value else []

def skill_counts(skill, *modifiers):
    return skill + sum(max(0, m) for m in modifiers), sum(max(0, -m) for m in modifiers)

def result_text(positive, penalty):
    return f'Успехов: {positive} − {penalty} = {max(0, positive-penalty)}.' if penalty else f'Успехов: {positive}.'
