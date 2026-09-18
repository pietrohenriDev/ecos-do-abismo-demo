# Ecos do Abismo — Demo Estável

Demo pública de boss fight em Python + Pygame.

## Executar

```powershell
py -3 -m pip install pygame
py -3 main.py
```

## Controles

- **A/D** ou setas: mover
- **Espaço/W/↑**: pular, com pulo duplo
- **J/X**: atacar
- **Shift**: esquivar
- **R**: reiniciar depois de vencer ou perder
- **Esc**: sair

## Escopo

Esta primeira versão tem um único chefe, o **Rei do Abismo**, com duas fases. A prioridade é estabilidade, leitura do combate e sensação de impacto antes da expansão de conteúdo.

A luta usa:

- introdução cinematográfica;
- telegráficos quentes antes do dano;
- flash e partículas no impacto;
- transformação agressiva na metade da vida;
- pressão visual da arena;
- vórtices e ondas de partículas;
- timing controlado para cada padrão.
