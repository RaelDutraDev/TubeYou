"""Ponto de entrada isolado. O servidor controla o tempo de toda a árvore."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from erros import classificar_erro
from midia import obter_formatos, preparar_download


def main():
    pasta = Path(sys.argv[1]).resolve()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s",
                        handlers=[RotatingFileHandler(pasta / "worker.log", maxBytes=262144,
                                                      backupCount=1, encoding="utf-8")])
    try:
        entrada = json.loads((pasta / "entrada.json").read_text(encoding="utf-8"))
        if entrada["tarefa"] == "formatos":
            resultado = obter_formatos(entrada["dados"]["url"])
        elif entrada["tarefa"] == "download":
            resultado = preparar_download(entrada["dados"], pasta)
        else:
            raise RuntimeError("Tarefa desconhecida")
        saida = {"ok": True, "resultado": resultado}
    except Exception as erro:
        logging.exception("Falha na operação")
        saida = {"ok": False, **classificar_erro(erro).publico()}
    (pasta / "resultado.json").write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
