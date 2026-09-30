# Linhas de base de qualidade

Relatórios gerados com `translaterany report <série> --json docs/baselines/<data>-<marco>-<série>.json`
ao fim de cada marco (M5 em diante). Contêm **apenas números agregados** — nunca trechos de legenda.

Comparar um marco com a linha de base anterior:

    translaterany report <série> --baseline docs/baselines/<arquivo>.json
