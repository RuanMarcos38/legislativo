"""Exact, explicit calculations shared by dashboards and exports."""
from decimal import Decimal,InvalidOperation
from datetime import datetime,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError

def number(value):
    if isinstance(value,(float,bool)):raise ValueError('Use texto decimal')
    try:d=Decimal(str(value))
    except (InvalidOperation,TypeError):raise ValueError('Valor inválido')
    if not d.is_finite():raise ValueError('Valor inválido')
    return d

def text(value):return format(value.quantize(Decimal('.000001')),'f').rstrip('0').rstrip('.') if value else '0'

def change(current,previous,rate=False):
    a,b=number(current),number(previous)
    return dict(absolute=text(a-b),percentage=text((a-b)/b*100) if b>0 else None,
      points=text(a-b) if rate else None,formula='((atual − anterior) / anterior) × 100',
      note='Variação percentual não aplicável para base zero ou negativa.' if b<=0 else 'Comparação entre observações consecutivas; não indica causalidade.')

def ratio(numerator,denominator):
    n,d=number(numerator),number(denominator)
    return dict(numerator=str(numerator),denominator=str(denominator),value=text(n/d*100) if d>0 else None,formula='numerador / denominador × 100')

def deflate(value,index_at_period,index_at_reference):
    a,b=number(index_at_period),number(index_at_reference)
    if a<=0 or b<=0:raise ValueError('Índice inválido')
    return text(number(value)*b/a)

def brasilia(value=None):
    stamp=datetime.fromisoformat(value.replace('Z','+00:00')) if value else datetime.now(timezone.utc)
    if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
    try:tz=ZoneInfo('America/Sao_Paulo')
    except ZoneInfoNotFoundError:
        # Modern timestamps only; historical conversion requires the IANA timezone database.
        if stamp.year<2020:raise ValueError('Base de fuso histórico indisponível')
        from datetime import timedelta
        tz=timezone(timedelta(hours=-3))
    return stamp.astimezone(tz).strftime('%d/%m/%Y %H:%M:%S')+' — Horário de Brasília'
