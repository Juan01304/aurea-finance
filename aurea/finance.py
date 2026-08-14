from __future__ import annotations
import calendar,re
from datetime import date,datetime

def month_key(v=None):
    if v and re.fullmatch(r'\d{4}-\d{2}',v):
        y,m=map(int,v.split('-'))
        if 2000<=y<=2100 and 1<=m<=12:return v
    return date.today().strftime('%Y-%m')
def shift_month(mon,d):
    y,m=map(int,mon.split('-'));i=y*12+m-1+d;return f'{i//12:04d}-{i%12+1:02d}'
def days_left_in_month(mon):
    y,m=map(int,mon.split('-'));last=calendar.monthrange(y,m)[1];t=date.today()
    if (y,m)<(t.year,t.month):return 1
    if (y,m)>(t.year,t.month):return last
    return max(1,last-t.day+1)
def money(v,locale='pt-BR'):
    s=f'R$ {v:,.2f}';return s if locale.startswith('en') else s.replace(',','X').replace('.',',').replace('X','.')
def extract_amount(text):
    xs=re.findall(r'(?:r\$\s*)?(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})|\d+(?:[.,]\d{1,2})?)',text.lower())
    if not xs:return None
    t=xs[-1]
    if '.' in t and ',' in t:t=t.replace('.','').replace(',','.')
    elif ',' in t:t=t.replace(',','.')
    try:return float(t)
    except:return None

def calculate_snapshot(profile,bills,transactions,goals,budgets,statuses,month):
    base=float(profile.get('monthly_income') or 0);extra=sum(float(t['amount']) for t in transactions if t['tx_type']=='income');spent=sum(float(t['amount']) for t in transactions if t['tx_type']=='expense');committed=sum(float(b['amount']) for b in bills);paid=sum(float(b['amount']) for b in bills if statuses.get(int(b['id']),False));unpaid=max(0,committed-paid);income=base+extra;remain=income-committed-spent;pct=float(profile.get('investment_pct') or 10);desired=max(0,income*pct/100);ratio=committed/income if income else 0
    if remain<=0:suggested=0.0
    else:
        cap=.70 if ratio<.40 else .55 if ratio<.65 else .35 if ratio<.85 else .20;suggested=min(desired,remain*cap)
    safe=max(0,remain-suggested);deficit=max(0,-remain);days=days_left_in_month(month);daily=safe/days
    cats={}
    for t in transactions:
        if t['tx_type']=='expense':cats[t['category']]=cats.get(t['category'],0)+float(t['amount'])
    limits={b['category']:float(b['monthly_limit']) for b in budgets};bp=[];breaches=0
    for cat,lim in sorted(limits.items()):
        sp=cats.get(cat,0);over=bool(lim and sp>lim);breaches+=int(over);bp.append({'category':cat,'limit':round(lim,2),'spent':round(sp,2),'remaining':round(max(0,lim-sp),2),'pct':round(sp/lim*100,1) if lim else 0,'breached':over})
    score=100.0;factors=[]
    if income<=0:score=0;factors=[{'label':'Renda não cadastrada','impact':-100,'tone':'danger'}]
    else:
        if ratio>.50:
            imp=min(35,(ratio-.50)*90);score-=imp;factors.append({'label':'Compromissos fixos altos','impact':-round(imp),'tone':'warning'})
        spr=spent/income
        if spr>.25:
            imp=min(25,(spr-.25)*75);score-=imp;factors.append({'label':'Gastos variáveis altos','impact':-round(imp),'tone':'warning'})
        if deficit:score-=35;factors.append({'label':'Mês em déficit','impact':-35,'tone':'danger'})
        if breaches:
            imp=min(15,breaches*5);score-=imp;factors.append({'label':f'{breaches} orçamento(s) excedido(s)','impact':-imp,'tone':'warning'})
        if suggested:
            bonus=min(10,suggested/income*50);score+=bonus;factors.append({'label':'Espaço para reserva','impact':round(bonus),'tone':'good'})
    score=int(max(0,min(100,round(score))));today=date.today();current=month==today.strftime('%Y-%m');display=[];overdue=[];upcoming=[]
    for b in sorted(bills,key=lambda x:(int(x['due_day']),str(x['name']))):
        item=dict(b);item['paid']=statuses.get(int(b['id']),False);item['overdue']=bool(current and not item['paid'] and int(b['due_day'])<today.day);display.append(item)
        if item['overdue']:overdue.append(item)
        if not item['paid']:upcoming.append(item)
    gs=[]
    for g in goals:
        target=float(g['target_amount']);cur=float(g['current_amount']);prog=cur/target*100 if target else 0;need=None
        if g.get('target_date'):
            try:
                td=datetime.strptime(g['target_date'],'%Y-%m-%d').date();months=max(1,(td.year-today.year)*12+td.month-today.month);need=max(0,target-cur)/months
            except:pass
        gs.append({**g,'progress_pct':round(min(100,prog),1),'monthly_needed':round(need,2) if need is not None else None})
    return {'profile':profile,'month':month,'bills':display,'transactions':transactions,'goals':gs,'budgets':bp,'category_totals':cats,'upcoming_bills':upcoming,'overdue_bills':overdue,'health_factors':factors,'metrics':{'income_base':round(base,2),'extra_income':round(extra,2),'total_income':round(income,2),'committed':round(committed,2),'paid_bills':round(paid,2),'unpaid_bills':round(unpaid,2),'variable_spent':round(spent,2),'remaining_before_save':round(remain,2),'desired_save':round(desired,2),'suggested_save':round(suggested,2),'safe_to_spend':round(safe,2),'deficit':round(deficit,2),'daily_safe':round(daily,2),'days_left':days,'committed_pct':round(ratio*100,1) if income else 0,'health_score':score,'investment_pct':pct,'budget_breaches':breaches}}

def build_insights(s):
    m=s['metrics'];out=[]
    if m['total_income']<=0:return [{'tone':'neutral','title':'Comece pela renda','body':'Cadastre quanto entra por mês para liberar os cálculos de limite e reserva.'}]
    if s['overdue_bills']:out.append({'tone':'danger','title':'Contas vencidas','body':f"Há {len(s['overdue_bills'])} conta(s) vencida(s), somando {money(sum(float(x['amount']) for x in s['overdue_bills']))}."})
    if m['committed_pct']>=80:out.append({'tone':'warning','title':'Pouca elasticidade','body':f"{m['committed_pct']:.0f}% da renda já nasce comprometida. Evite transformar gasto variável em nova parcela fixa."})
    elif m['committed_pct']<50:out.append({'tone':'good','title':'Boa margem estrutural','body':'Seus compromissos fixos estão abaixo de metade da renda. Use parte da folga para construir reserva.'})
    top=sorted(s['category_totals'].items(),key=lambda x:x[1],reverse=True)
    if top:out.append({'tone':'neutral','title':f'Maior categoria: {top[0][0]}','body':f'Você registrou {money(top[0][1])} nessa categoria no mês.'})
    bad=[b for b in s['budgets'] if b['breached']]
    if bad:
        b=bad[0];out.append({'tone':'warning','title':f"Orçamento de {b['category']} estourou",'body':f"O limite era {money(b['limit'])} e o gasto chegou a {money(b['spent'])}."})
    if m['suggested_save']>0:out.append({'tone':'good','title':'Reserva possível','body':f"Aurea sugere separar {money(m['suggested_save'])} sem reduzir seu teto livre a zero."})
    return out[:4]
