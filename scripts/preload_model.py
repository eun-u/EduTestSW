"""
모델(토크나이저 포함)을 '미리 캐시에 받아두기' 또는 '런타임 로딩'하는 공용 모듈.

[CLI 사용 예시]
1) 캐시만 받아두기(모델 메모리 로딩 없이 빠르게):
   python scripts/preload_model.py --download-only

2) 실제 로딩까지 확인(토크나이저/모델 메모리 로딩):
   python scripts/preload_model.py

[런타임 사용]
from scripts.preload_model import get_tokenizer_model
select 1) tokenizer, model = get_tokenizer_model()  # 최초 1회 로딩, 이후 재사용
select 2) tokenizer, model = get_tokenizer_model(verbose=False)  # 로그 없이 1회 로딩
"""
from __future__ import annotations

import argparse
import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from typing import Optional, Tuple

try:
    from huggingface_hub import snapshot_download
except Exception:
    snapshot_download = None  # 설치 안 되어도 런타임 로딩에는 지장 없음
    
# -----------------------------
# 설정
# -----------------------------
CHECKPOINT = os.environ.get("EDU_MODEL_CHECKPOINT", "bigcode/starcoder2-3b")

if torch.backends.mps.is_available():
    DEVICE = "mps"
elif torch.cuda.is_available():
    DEVICE = "cuda"
else:
    DEVICE = "cpu"

# mps/cuda는 float16, cpu는 float32 권장
DTYPE = torch.float16 if DEVICE in ("mps", "cuda") else torch.float32


# -----------------------------
# 모듈 내부 싱글톤 (프로세스 내 1회만 로드)
# -----------------------------
TOKENIZER = None
MODEL = None

def log(msg: str, verbose: bool):
    if verbose:
        print(msg)
        

def download_only(verbose: bool = True) -> None:
    """
    모델 파일을 캐시에만 내려받는다. (메모리 로딩 없음)
    """
    if snapshot_download is None:
        print("[preload] huggingface_hub 미설치로 download-only는 생략됩니다.")
        return
    cache_dir = os.environ.get("HF_HOME")  # 설정되어 있다면 해당 경로 사용
    print(f"[preload] snapshot_download: repo_id={CHECKPOINT}, cache_dir={cache_dir or '(default)'}")
    snapshot_download(repo_id=CHECKPOINT, local_files_only=False)
    print("[preload] 캐시 다운로드 완료")


def load_runtime(verbose: bool = True) -> Tuple[AutoTokenizer, AutoModelForCausalLM]:
    """
    토크나이저/모델을 실제 메모리에 로드. 캐시에 있으면 재다운로드 없음.
    """
    global TOKENIZER, MODEL
    if TOKENIZER is not None and MODEL is not None:
        return TOKENIZER, MODEL

    log(f"[preload] device={DEVICE}", verbose)
    TOKENIZER = AutoTokenizer.from_pretrained(CHECKPOINT)
    MODEL = AutoModelForCausalLM.from_pretrained(CHECKPOINT, torch_dtype=DTYPE)
    MODEL = MODEL.to(DEVICE)

    # pad/eos 안전 설정(일부 모델에서 pad 누락되는 문제 대응)
    if getattr(TOKENIZER, "pad_token_id", None) is None:
        eos_tok = getattr(TOKENIZER, "eos_token", None)
        if eos_tok is not None:
            TOKENIZER.pad_token = eos_tok

    log("[preload] 모델 로딩 완료 (캐시 사용 가능)", verbose)
    return TOKENIZER, MODEL


def get_tokenizer_model(verbose: bool = False) -> Tuple[AutoTokenizer, AutoModelForCausalLM]:
    """런타임 진입점. 기본은 조용히(verbose=False) 1회만 로드."""
    return load_runtime(verbose=verbose)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-only", action="store_true", help="모델 파일만 캐시에 내려받고 종료")
    args = parser.parse_args()

    if args.download_only:
        download_only()
    else:
        load_runtime()
        print("모델 다운로드/로딩 완료 (캐시).")


if __name__ == "__main__":
    main()