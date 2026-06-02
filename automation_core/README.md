# Automation Core

Pacote paralelo para tornar automacoes de navegador mais previsiveis.

Ele ainda nao e usado pelo fluxo atual. A ideia e migrar uma tela por vez,
quando uma etapa estiver pronta para testar.

## Ideia

Em vez de escrever uma sequencia fragil de cliques, cada campo vira uma
declaracao:

```python
from automation_core import FieldSpec, FieldType, StepSpec, run_step

step = StepSpec(
    name="dados-basicos",
    fields=[
        FieldSpec(
            name="processo",
            value="23080.012345/2026-01",
            selectors=("#txtprocesso:visible",),
            field_type=FieldType.TEXT,
            retries=3,
        ),
    ],
)

result = run_step(page, step, artifact_dir="/tmp/autoliquid-automation")
```

Cada campo tenta preencher, dispara eventos, espera estabilizar, le de volta e
repete se o site apagar ou reformatar o valor.

## Componentes

- `models.py`: contratos declarativos de campos e etapas.
- `strategies.py`: estrategias de preenchimento e validacao.
- `runner.py`: executa uma etapa com pre/post-condicoes.
- `diagnostics.py`: salva screenshot, HTML e manifesto basico em falhas.
- `manifest.py`: captura campos/botoes visiveis para comparar telas.

## Proximo passo

Escolher uma tela pequena e instavel para criar o primeiro `StepSpec` real.

## Piloto: Principal com Orcamento

O modulo `automation_core.comprasnet_principal` monta etapas declarativas para
os empenhos de Principal com Orcamento. Ele fica em paralelo: nenhum fluxo atual
o chama automaticamente.

```python
from automation_core.comprasnet_principal import (
    PrincipalPilotOptions,
    run_principal_orcamento_pilot,
)

results = run_principal_orcamento_pilot(
    page,
    dados_extraidos,
    PrincipalPilotOptions(dry_run=True),
)
```

Use `dry_run=False` apenas quando quisermos testar o clique de confirmacao.
