"""
comprasnet_finalizar.py
Clica no botão 'Apropriar SIAFI'.
"""
import time
from comprasnet.base import conectar

def executar():
    p, pagina = conectar()
    try:
        print("=== FINALIZAR PROCESSO (APROPRIAR SIAFI) ===")
        
        # Localiza o botão pelo ID mostrado no DOM
        btn_apropriar = pagina.locator("#btnEnviarApropriacaoSiafiDiretamente")
        
        # Verifica se o botão está visível e pronto para ser clicado
        btn_apropriar.wait_for(state="visible", timeout=5000)
        
        # Clica no botão
        btn_apropriar.click()
        
        # Aguarda 2 segundos para dar tempo do sistema processar a ação
        time.sleep(2.0)
        
        return {"status": "sucesso", "mensagem": "Apropriação SIAFI enviada com sucesso!"}

    except Exception as e:
        return {"status": "erro", "mensagem": f"Erro ao clicar em Apropriar SIAFI: {e}"}
    finally:
        p.stop()