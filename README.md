# DownVid — YouTube Downloader (PySide6, tema escuro)

Aplicativo com interface moderna (tema escuro) para baixar vídeos do YouTube:

- Baixa um único vídeo (colando a URL) ou uma playlist inteira.
- Opção para baixar **vídeo (MP4/MKV)** ou **áudio (MP3)**.
- Suporta **múltiplos downloads simultâneos**, com ajuste do número de downloads paralelos.
- Mostra **progresso por item**, velocidade, ETA e status.
- **Pausar, retomar e cancelar** por tarefa e em lote.
- Aba de **concluídos** com lista dos arquivos baixados.
- Preferência de **qualidade de vídeo**: Auto, 2160p, 1440p, 1080p, 720p, 480p, 360p.
- **Qualidade do MP3**: 320/256/192/160/128 kbps.
- **Legendas**: baixar por idiomas (ex.: `pt,en`) e opção de **incorporar** legendas ao arquivo final.
- **Exportar/Importar fila** (JSON).
- **Histórico persistente**: restaura concluídos e oferece recarregar a fila salva na abertura.
- **Retomada de downloads** interrompidos (continuation com `yt-dlp`).

> Este projeto é para fins educacionais. Respeite sempre os Termos de Serviço do YouTube e as leis de direitos autorais. Baixe apenas conteúdo para o qual você possui os direitos.

## Requisitos

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) no PATH (necessário para MP3, mesclar vídeo/áudio e incorporar legendas).
- Dependências Python:
  ```bash
  pip install -r requirements.txt
  ```

## Executando

```bash
python main.py
```

## Uso

1. Cole uma URL de vídeo ou de playlist do YouTube no campo de texto.
   - Você pode colar **várias URLs** (uma por linha) para adicionar vários itens de uma vez.
2. Escolha o tipo: **Vídeo (MP4/MKV)** ou **Áudio (MP3)**.
3. Para vídeo, selecione a **qualidade** e, se desejar, ative **legendas** (defina idiomas e se quer incorporar).
   - Para incorporar legendas, o formato **MKV** é geralmente mais compatível. MP4 usa `mov_text`.
4. Para áudio, selecione a **qualidade do MP3**.
5. Ajuste o número de **downloads simultâneos**.
6. Escolha a **pasta de destino**.
7. Clique em **Adicionar à fila**.
8. Use os botões de **Pausar**, **Retomar** e **Cancelar** por linha, ou os botões “Pausar todos”, “Retomar todos” e “Cancelar selecionados”.

## Notas técnicas

- O app usa `yt-dlp` via API com hooks de progresso. Para pausa, aplica espera cooperativa. Cancelar lança `DownloadCancelled`.
- Para playlist, expande as entradas e cria uma tarefa por vídeo, permitindo paralelismo real entre vídeos.
- O limite de paralelismo é controlado por `QThreadPool.setMaxThreadCount(...)` e pode ser alterado a qualquer momento.
- Os arquivos são nomeados como `%(title)s [%(id)s].%(ext)s` para reduzir colisões.
- Subtítulos:
  - Se “Baixar legendas” estiver marcado, usa `writesubtitles=True`, `subtitleslangs` (ex.: `["pt","en"]`) e formato `srt/best`.
  - Se “Incorporar legendas” estiver marcado, usa `embedsubtitles=True` (requer ffmpeg).
  - Para máxima compatibilidade ao incorporar várias faixas, prefira container **MKV**.
- Retomada: `continuedl=True` permite continuar downloads parciais.
- Persistência:
  - O estado da fila e a lista de concluídos são salvos em `app_state.json`.
  - Ao iniciar, o app oferece recarregar a fila anterior.

## Solução de problemas

- “FFmpeg não encontrado”: instale o ffmpeg e garanta que `ffmpeg` esteja no PATH.
- Erros intermitentes de rede: `yt-dlp` está configurado com tentativas de repetição.
- Qualidade de vídeo indisponível: o YouTube pode não ter a resolução desejada; o app tentará o melhor disponível até o limite escolhido.
- MP3 com qualidade específica: ajuste a qualidade do `FFmpegExtractAudio` no menu.

## Licença

Uso educacional. Verifique as implicações legais no seu país antes de usar.