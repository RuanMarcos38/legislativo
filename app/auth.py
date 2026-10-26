import argparse,getpass,hashlib,hmac,secrets,time
from .db import connect
ROLES={"superadmin":3,"admin":2,"analyst":1,"reader":0}
def password_hash(password,salt=None):
    if len(password)<12 or len(password)>256: raise ValueError("Senha deve ter de 12 a 256 caracteres")
    salt=salt or secrets.token_hex(16)
    digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return salt+":"+digest
def verify(password,stored):
    try: return hmac.compare_digest(password_hash(password,stored.split(":")[0]),stored)
    except (ValueError,TypeError): return False
def create_user(db,tenant_name,email,password,role="admin",existing_tenant=None):
    if role not in ROLES or "@" not in email or len(email)>254: raise ValueError("Usuário inválido")
    tenant=existing_tenant or secrets.token_hex(16);uid=secrets.token_hex(16)
    if existing_tenant:
        if not db.execute("SELECT id FROM tenants WHERE id=?",(tenant,)).fetchone(): raise ValueError("Organização inexistente")
    else: db.execute("INSERT INTO tenants VALUES(?,?)",(tenant,tenant_name))
    db.execute("INSERT INTO users VALUES(?,?,?,?,?)",(uid,tenant,email.strip().lower(),password_hash(password),role));db.commit()
    return tenant,uid
def login(db,email,password):
    row=db.execute("SELECT * FROM users WHERE email=?",(email.strip().lower(),)).fetchone()
    # Apply comparable work for unknown accounts.
    stored=row["password_hash"] if row else "00"*16+":"+"00"*64
    valid=verify(password,stored)
    if not row or not valid: return None
    sid=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    db.execute("DELETE FROM sessions WHERE expires_at<?",(time.time(),))
    db.execute("INSERT INTO sessions VALUES(?,?,?,?)",(hashlib.sha256(sid.encode()).hexdigest(),row["id"],csrf,time.time()+8*3600));db.commit()
    return sid,csrf
def session(db,token):
    if not token: return None
    row=db.execute("SELECT u.id,u.tenant_id,u.email,u.role,s.csrf,t.name tenant FROM sessions s JOIN users u ON u.id=s.user_id JOIN tenants t ON t.id=u.tenant_id WHERE s.id=? AND s.expires_at>?",(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
    return dict(row) if row else None
def require(user,role):
    if not user or ROLES.get(user["role"],-1)<ROLES[role]: raise PermissionError("Acesso não autorizado")
def watches(db,user):
    require(user,"reader")
    return [dict(r) for r in db.execute("SELECT id,query,created_at FROM watches WHERE tenant_id=? ORDER BY id DESC",(user["tenant_id"],))]
def events(db,user):
    require(user,"reader")
    return [dict(r) for r in db.execute("SELECT e.*,w.query,r.data FROM events e JOIN watches w ON w.id=e.watch_id JOIN records r ON r.id=e.record_id WHERE w.tenant_id=? ORDER BY e.id DESC LIMIT 100",(user["tenant_id"],))]
def plan(db,user):
    require(user,"reader")
    row=db.execute("SELECT p.* FROM plans p WHERE p.id=COALESCE((SELECT plan_id FROM tenant_plans WHERE tenant_id=?),'free')",(user["tenant_id"],)).fetchone()
    result=dict(row);result["watch_count"]=db.execute("SELECT count(*) FROM watches WHERE tenant_id=?",(user["tenant_id"],)).fetchone()[0]
    result["billing"]="Não ativado; plano administrativo sem cobrança"
    return result
if __name__=="__main__":
    p=argparse.ArgumentParser(description="Criar organização e administrador sem registrar senha em argumentos.")
    p.add_argument("--tenant",default="Organização");p.add_argument("--tenant-id",help="ID existente para adicionar usuário à mesma organização");p.add_argument("--email",required=True);p.add_argument("--role",choices=list(ROLES),default="admin")
    args=p.parse_args();password=getpass.getpass("Senha (mínimo 12 caracteres): ")
    if password!=getpass.getpass("Repita a senha: "): raise SystemExit("Senhas diferentes")
    with connect() as db: create_user(db,args.tenant,args.email,password,args.role,args.tenant_id)
    print("Organização e usuário criados. Consulte o ID da organização em Configurações.")
