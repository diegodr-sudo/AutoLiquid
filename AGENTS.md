# Guia Rápido Para Revisão por IA

## Objetivo
Este projeto automatiza fluxo de liquidação no Comprasnet/Contratos.gov.br, com interface PyQt6 e automações Playwright.

## Ordem recomendada de leitura
1. `interface.py`
2. `ui/bootstrap.py`
3. `interface_main.py`
4. `interface_telas.py`
5. `interface_workers.py`
6. `comprasnet_base.py`
7. Arquivo da etapa específica (`comprasnet_*`, `extrator.py`, `datas_impostos.py`)

## Mapa curto dos módulos
- `interface.py`: ponto de entrada mínimo.
- `ui/bootstrap.py`: cria `QApplication` e janela principal.
- `interface_main.py`: shell principal da UI, navegação e disparo dos workers.
- `interface_telas.py`: telas de upload/resultados e parte importante do fluxo visual.
- `interface_dialogos.py`: diálogos de configuração e tabelas.
- `interface_workers.py`: threads, extração assíncrona e painel de log.
- `comprasnet_base.py`: conexão com Chrome/Playwright e helpers compartilhados da automação.
- `comprasnet_*.py`: etapas do preenchimento no portal.
- `extrator.py`: parsing do PDF de liquidação.
- `datas_impostos.py`: cálculo de vencimentos e regras fiscais.
- `services/config_service.py`: persistência de configurações/tabelas.
- `core/app_paths.py`: caminhos e constantes centrais.

## Arquivos caros para contexto
- `interface_telas.py`: arquivo grande de UI; leia por seções.
- `solar_fila.py`: automação extensa e mais isolada do fluxo principal.
- `interface_dialogos.py`: grande, mas focado em tabelas/configuração.

## O que pular primeiro
- `__pycache__/`
- `.venv/`
- `.opencode/`
- `erros.log`
- binários e PDFs locais

## Pontos de atenção
- Há lógica de negócio misturada com UI em alguns arquivos grandes.
- Existem automações antigas ainda na raiz; valide se o fluxo usa serviço central antes de refatorar.
- `services/config_service.py` e `core/*` devem ser preferidos para caminhos/configuração compartilhada.
