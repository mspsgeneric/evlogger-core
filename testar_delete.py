import os
from dotenv import load_dotenv
from util.supabase import get_supabase

# Carrega o .env
load_dotenv()
supabase = get_supabase()

guild_id_para_excluir = "1241774023277543484"

# Verificar registros atuais
dados_atuais = supabase.table("emails").select("guild_id").execute()
print(f"📋 Dados no Supabase: {dados_atuais.data}")

for item in dados_atuais.data:
    print(f"🧪 guild_id armazenado: '{item['guild_id']}' == '{guild_id_para_excluir}' → {item['guild_id'] == guild_id_para_excluir}")

print(f"\n🧹 Tentando deletar guild_id = {guild_id_para_excluir}...")
try:
    resposta = supabase.table("emails").delete().eq("guild_id", guild_id_para_excluir).execute()
    print(f"✅ Deletado com sucesso! Resposta: {resposta.data}")
except Exception as e:
    print(f"❌ Erro ao deletar: {e}")
