# Guia Obrigatório Para Agentes de IA

## Leitura obrigatória
Antes de executar comandos, alterar arquivos ou propor refatorações neste repositório, todo agente de IA deve ler este arquivo. Este documento é o contrato de trabalho do AutoLiquid: se uma instrução local conflitar com uma preferência genérica do agente, siga este arquivo e os padrões já existentes no código.

## Objetivo
Este projeto automatiza fluxo de liquidação no Comprasnet/Contratos.gov.br, com interface PyQt6 e automações Playwright.

## Regras de UI e UX
- Priorize consistência visual antes de criar um componente novo. Se dois controles têm a mesma função ou peso visual, eles devem ter altura, raio de borda, espaçamento e estados de foco equivalentes.
- Campos de formulário em modais e painéis operacionais devem usar formato arredondado/pílula quando estiverem no mesmo grupo visual. Não misture `select` com aparência quadrada e `input` arredondado no mesmo bloco.
- Use controles nativos de forma previsível: `select` para escolha fechada, `input` numérico para números, switch/checkbox para binários e botões com ícone para ações explícitas.
- Cards e seções podem manter `rounded-2xl`; botões e campos dentro deles devem seguir um raio coerente entre si, sem alternar entre quadrado, `rounded-md` e pílula no mesmo formulário.
- Textos de ajuda devem ser curtos, alinhados ao grupo que explicam e não competir com os campos principais.
- Configurações globais devem exibir o indicador `GlobalScopeIcon`; preferências locais/de máquina, como tema, navegador, porta, colunas visíveis e layout da fila, não devem receber o globo.
- Antes de finalizar qualquer alteração visual, rode pelo menos `npm --prefix frontend run build`. Quando houver impacto de layout, abra o app em desenvolvimento e confira a tela afetada.

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
