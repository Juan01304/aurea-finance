from __future__ import annotations
import json,os,urllib.error,urllib.request
from .finance import extract_amount,money
from .security import safety_identifier
DEFAULT_MODEL='gpt-5.6-luna'
def local_assistant(message,snapshot,locale='pt-BR'):
    m=snapshot['metrics'];q=message.lower().strip();amt=extract_amount(q);en=locale.startswith('en')
    if m['total_income']<=0:return 'Add your monthly income first.' if en else 'Cadastre sua renda mensal primeiro. Sem uma base de entrada, qualquer limite seria só um palpite bem vestido.'
    if amt is not None and any(k in q for k in ['comprar','gastar','posso','custa','compra','spend','buy','cost']):
        after=m['safe_to_spend']-amt
        if amt<=m['safe_to_spend']:return f"Yes. You would still have {money(after,'en-US')} available." if en else f"Sim. {money(amt)} cabe no seu teto livre. Depois da compra, sobrariam {money(after)} até o fim do mês."
        return f"I would not classify it as safe. It is {money(amt-m['safe_to_spend'],'en-US')} above your ceiling." if en else f"Eu não classificaria essa compra como segura agora. Ela passa seu teto livre em {money(amt-m['safe_to_spend'])}."
    if any(k in q for k in ['gastar','livre','disponível','disponivel','quanto posso','safe','available']):return f"You have {money(m['safe_to_spend'],'en-US')} safely available." if en else f"Seu teto seguro até o fim do mês é {money(m['safe_to_spend'])}, cerca de {money(m['daily_safe'])} por dia."
    if any(k in q for k in ['invest','guardar','reserva','poupar','save']):return f"Eu separaria {money(m['suggested_save'])} agora. Sua meta configurada é {m['investment_pct']:.0f}% da renda." if not en else f"I would set aside {money(m['suggested_save'],'en-US')} now."
    if any(k in q for k in ['venc','atras','próxim','proxim','due','overdue']):
        if snapshot['overdue_bills']:return f"Você tem {len(snapshot['overdue_bills'])} conta(s) vencida(s), somando {money(sum(float(b['amount']) for b in snapshot['overdue_bills']))}."
        up=snapshot['upcoming_bills'][:4];return 'As próximas pendentes são: '+ '; '.join(f"{b['name']} dia {b['due_day']} ({money(float(b['amount']))})" for b in up)+'.' if up else 'Não há contas recorrentes pendentes neste mês.'
    if any(k in q for k in ['cortar','reduzir','economizar','maior gasto','cut']):
        top=sorted(snapshot['category_totals'].items(),key=lambda x:x[1],reverse=True)[:3]
        return 'Eu começaria por '+', '.join(f'{n}: {money(v)}' for n,v in top)+'. Procure gastos repetidos ou adiáveis.' if top else 'Ainda não há despesas variáveis suficientes para apontar um corte com fundamento.'
    if any(k in q for k in ['orçamento','orcamento','budget']):
        bad=[b for b in snapshot['budgets'] if b['breached']]
        if bad:
            b=bad[0];return f"O orçamento de {b['category']} passou do limite em {money(b['spent']-b['limit'])}."
        return 'Seus limites por categoria estão dentro do planejado.' if snapshot['budgets'] else 'Você ainda não criou limites por categoria.'
    if any(k in q for k in ['meta','objetivo','goal']):
        if not snapshot['goals']:return 'Crie uma meta com valor e data para eu calcular o ritmo.'
        g=snapshot['goals'][0];left=max(0,float(g['target_amount'])-float(g['current_amount']));extra=f" O ritmo aproximado é {money(g['monthly_needed'])}/mês." if g.get('monthly_needed') is not None else ''
        return f"Sua meta “{g['name']}” está em {g['progress_pct']:.0f}%. Faltam {money(left)}.{extra}"
    if any(k in q for k in ['cartão','cartao','card']):
        total=sum(float(b['amount']) for b in snapshot['bills'] if b.get('kind')=='card');return f"As faturas cadastradas somam {money(total)}, {(total/m['total_income']*100 if m['total_income'] else 0):.0f}% da renda."
    if any(k in q for k in ['saúde','saude','situação','situacao','como estou','score','health']):return f"Sua Saúde do Orçamento está em {m['health_score']}/100. Contas recorrentes comprometem {m['committed_pct']:.0f}% da renda e seu teto livre é {money(m['safe_to_spend'])}."
    return f"Neste mês entram {money(m['total_income'])}, há {money(m['committed'])} em contas e {money(m['variable_spent'])} em gastos variáveis. Seu teto livre é {money(m['safe_to_spend'])}."
def openai_assistant(message,snapshot,locale,user_id,app_secret,history=None):
    key=os.environ.get('OPENAI_API_KEY','').strip()
    if not key:raise RuntimeError('OPENAI_API_KEY não configurada')
    model=os.environ.get('OPENAI_MODEL',DEFAULT_MODEL);ctx={'currency':'BRL','month':snapshot['month'],'metrics':snapshot['metrics'],'bills':[{k:b.get(k) for k in ['name','category','amount','due_day','kind','paid']} for b in snapshot['bills'][:10]],'recent_transactions':[{k:t.get(k) for k in ['description','category','amount','tx_type','tx_date']} for t in snapshot['transactions'][:15]],'budgets':snapshot['budgets'][:12],'goals':snapshot['goals'][:8],'overdue_count':len(snapshot['overdue_bills'])};lang='English' if locale.startswith('en') else 'Brazilian Portuguese'
    instr=f"You are Aurea, a concise personal budgeting copilot. Reply in {lang}. Use only FINANCIAL_CONTEXT for personalized numbers. The app calculations are authoritative. Help with budgeting, cash flow, category limits, goals, bill prioritization and purchase tradeoffs. Do not recommend specific stocks, crypto, leverage, gambling or casual new debt. Never claim to be a licensed adviser. If cash flow is negative or essentials are overdue, prioritize those. Keep answers practical and under 180 words."
    items=[]
    for x in (history or [])[-6:]:
        if x.get('role') in {'user','assistant'} and x.get('content'):items.append({'role':x['role'],'content':str(x['content'])[:800]})
    items.append({'role':'user','content':'FINANCIAL_CONTEXT:\n'+json.dumps(ctx,ensure_ascii=False)+'\n\nQUESTION:\n'+message})
    payload={'model':model,'store':False,'reasoning':{'effort':'low'},'max_output_tokens':650,'safety_identifier':safety_identifier(app_secret,user_id),'instructions':instr,'input':items}
    req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=45) as r:data=json.loads(r.read().decode())
    except urllib.error.HTTPError as e:raise RuntimeError(f'OpenAI HTTP {e.code}: '+e.read().decode(errors='replace')[:500]) from e
    parts=[]
    for item in data.get('output',[]):
        if item.get('type')=='message':
            for c in item.get('content',[]):
                if c.get('type')=='output_text' and c.get('text'):parts.append(c['text'])
    text='\n'.join(parts).strip()
    if not text:raise RuntimeError('Resposta vazia')
    return text
