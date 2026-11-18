"""Printable monthly report; browser Save as PDF preserves Thai text."""
from html import escape

def monthly_report(data, month):
    e=lambda v:escape(str(v),quote=True)
    cash=lambda n:f'THB {n/100:,.2f}'
    workspace=next(w for w in data['workspaces'] if w['id']==data['workspace_id'])
    rows=[t for t in data['transactions'] if t['date'].startswith(month)]
    total=lambda kind:sum(t['amount'] for t in rows if t['type']==kind)
    income,expense=total('income'),total('expense')
    accounts={a['id']:a['name'] for a in data['accounts']}
    def balance(a):
        tx=[t for t in data['transactions'] if t['date'][:7]<=month]
        return sum(r['delta'] for r in data.get('adjustments',[]) if r['account_id']==a['id'] and r['date'][:7]<=month)+a['opening']+sum((t['amount'] if t['type']=='income' else -t['amount']) for t in tx if t['account_id']==a['id'])+sum(t['amount'] for t in tx if t['type']=='transfer' and t['destination_id']==a['id'])
    closing=sum(balance(a) for a in data['accounts'])
    groups={}
    for t in rows:
        if t['type']=='expense':groups[t['category']]=groups.get(t['category'],0)+t['amount']
    body=''.join('<tr><td>'+e(t['date'])+'</td><td>'+e(t['description'])+'</td><td>'+e(t['type'])+'</td><td>'+e(t['category'])+'</td><td>'+e(accounts[t['account_id']]+(' → '+accounts[t['destination_id']] if t['type']=='transfer' else ''))+'</td><td class="num">'+e(('−' if t['type']=='expense' else '+' if t['type']=='income' else '↔')+cash(t['amount']))+'</td></tr>' for t in sorted(rows,key=lambda t:(t['date'],t['id'])))
    breakdown=''.join('<tr><td>'+e(k)+'</td><td class="num">'+cash(v)+'</td></tr>' for k,v in sorted(groups.items(),key=lambda p:-p[1]))
    plan=next((p for p in data['plans'] if p['month']==month),None)
    budget=''
    if plan:
        limits=''.join('<tr><td>'+e(r['category'])+'</td><td>'+cash(r['amount'])+'</td><td>'+cash(groups.get(r['category'],0))+'</td><td>'+cash(r['amount']-groups.get(r['category'],0))+'</td></tr>' for r in plan['limits'])
        items=''.join('<tr><td>'+e(r['description'])+'</td><td>'+e(r['category'])+'</td><td class="num">'+cash(r['amount'])+'</td></tr>' for r in plan['items'])
        budget='<h2>Budget & advance plan</h2><p>Monthly limit: '+('Not set' if plan['total'] is None else cash(plan['total']))+' · Remaining: '+('—' if plan['total'] is None else cash(plan['total']-expense))+'</p><p class="note">'+e(plan['notes'])+'</p>'
        if limits:budget+='<table><thead><tr><th>Category</th><th>Budget</th><th>Actual</th><th>Remaining</th></tr></thead><tbody>'+limits+'</tbody></table>'
        if items:budget+='<h3>Planned expenses (not recorded spending)</h3><table><thead><tr><th>Description</th><th>Category</th><th>Planned</th></tr></thead><tbody>'+items+'</tbody></table>'
    adjustment_rows=''.join('<tr><td>'+e(r['date'])+'</td><td>'+e(accounts[r['account_id']])+'</td><td>'+e(r['reason'])+'</td><td>'+cash(r['delta'])+'</td></tr>' for r in data.get('adjustments',[]) if r['date'].startswith(month))
    if adjustment_rows:budget+='<h2>Balance reconciliation (not income or spending)</h2><table><thead><tr><th>Date</th><th>Account</th><th>Reason</th><th>Adjustment</th></tr></thead><tbody>'+adjustment_rows+'</tbody></table>'
    balances=''.join('<tr><td>'+e(a['name'])+'</td><td class="num">'+cash(balance(a))+'</td></tr>' for a in data['accounts'])
    result = '''<!doctype html><html lang="th"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Cash Me Crying — '''+e(workspace['name'])+' — '+e(month)+'''</title><style>
body{font:13px/1.6 system-ui,sans-serif;color:#22332d;max-width:1000px;margin:35px auto;padding:0 22px}h1{margin:0;font-size:28px}h2{margin-top:30px;font-size:18px}.muted{color:#78847b}.summary{display:flex;flex-wrap:wrap;gap:25px;background:#f0f5f1;padding:20px}.summary b{display:block;font-size:20px}table{width:100%;border-collapse:collapse;margin:12px 0;overflow-wrap:anywhere}th,td{text-align:left;padding:9px;border-bottom:1px solid #dce3dd;vertical-align:top}th{background:#f5f7f5;font-size:11px}.num{text-align:right;white-space:nowrap}.note{white-space:pre-wrap}button{padding:12px 20px;background:#287867;color:white;border:0;border-radius:7px;cursor:pointer}.tools{margin-bottom:28px;padding:16px;background:#f3f6fa}.tools p{margin:5px 0}footer{margin-top:30px;font-size:10px;color:#78847b}@page{size:A4;margin:14mm}@media print{body{margin:0;padding:0;max-width:none;font-size:10px}.tools{display:none}thead{display:table-header-group}tr{break-inside:avoid}h2,h3{break-after:avoid}table{font-size:9px}.summary{background:white;border:1px solid #ddd;gap:20px}.summary b{font-size:15px}}
</style><div class="tools"><button onclick="window.print()">Print / Save as PDF</button><p>กดปุ่ม → Destination: Save as PDF → Save · บน Mac สามารถเลือก PDF → Save as PDF</p></div><h1>Cash Me Crying</h1><p class="muted">Track your spending. Try not to cry.</p><h2>'''+e(workspace['name'])+' · '+e(month)+'''</h2><div class="summary"><div>Income<b>'''+cash(income)+'</b></div><div>Expenses<b>'+cash(expense)+'</b></div><div>Monthly net<b>'+cash(income-expense)+'</b></div><div>Closing balance<b>'+cash(closing)+'</b></div></div><h2>Spending by category</h2><table><thead><tr><th>Category</th><th class="num">Spent</th></tr></thead><tbody>'+breakdown+'</tbody></table><h2>Account closing balances</h2><table><thead><tr><th>Account</th><th class="num">Balance</th></tr></thead><tbody>'+balances+'</tbody></table>'+budget+'<h2>Transactions</h2><table><thead><tr><th>Date</th><th>Description</th><th>Type</th><th>Category</th><th>Account</th><th class="num">Amount</th></tr></thead><tbody>'+body+'</tbody></table>'+('<p>No transactions in this month.</p>' if not rows else '')+'<footer>Generated locally · '+e(data['today'])+' · Transfers are excluded from income and expenses. Opening balances apply from the start of the ledger. Plans do not change balances.</footer></html>'

    color=workspace.get('theme','#287867')
    if not __import__('re').fullmatch(r'#[0-9a-fA-F]{6}',color):color='#287867'
    rgb=[int(color[i:i+2],16) for i in (1,3,5)]
    soft='#'+''.join(f'{round(v+(255-v)*.93):02x}' for v in rgb)
    return result.replace('#287867',color).replace('#f0f5f1',soft).replace('#22332d','#202a38').replace('#dce3dd','#e8ebef').replace('#78847b','#89909d')
