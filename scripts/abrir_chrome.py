"""
abrir_chrome.py
───────────────
Abre o Google Chrome com a porta de depuração remota configurada,
necessária para que os scripts Python de automação funcionem.

Usa um perfil dedicado (~/.chrome-comprasnet) para garantir uma instância
separada mesmo que o Chrome normal já esteja aberto.

Como usar:
  → Duplo clique neste arquivo   (macOS / Windows)
  → python abrir_chrome.py       (terminal)
"""
import time

from core.runtime_config import obter_porta_chrome
from services.chrome_service import abrir_chrome, chrome_esta_aberto


def main():
    porta = obter_porta_chrome()

    if chrome_esta_aberto(porta):
        print(f"✅ Chrome já está aberto e escutando na porta {porta}.")
        print("   Pode rodar os scripts Python normalmente.")
    else:
        print(f"🚀 Abrindo Chrome na porta {porta}...")
        print("⏳ Aguardando Chrome iniciar", end="", flush=True)
        abrir_chrome(porta)
        for _ in range(20):
            time.sleep(0.5)
            print(".", end="", flush=True)
            if chrome_esta_aberto(porta):
                print("\n✅ Chrome pronto! Agora você pode rodar os scripts Python.")
                break
        else:
            print(f"\n⚠️  Chrome não respondeu na porta {porta} após 10 segundos.")

    input("\nPressione Enter para fechar esta janela...")


if __name__ == "__main__":
    main()
