// 커버리지 계측 심(headless_pce.py PCE_COV) — beetle-pce 코어의 뱅크 0x68~0x87(SysCardRAM 192KB + CDRAM 64KB) 읽기·쓰기 처리기를 갈아 끼워
// 바이트마다 「명령 첫 바이트 인출(1) · 그 밖 읽기(2) · 쓰기(4) · 피연산자 인출(8)」 을 적는다. 빌드: gcc -O2 -shared -fPIC -o cov_shim.so cov_shim.c
// 명령 첫 바이트 = 처리기를 부른 자리가 RunSub 의 명령 인출 자리(g_opsite)일 때. 피연산자 = 읽는 논리 주소(HuCPU+0x70)가 PC(HuCPU+0x24)와 같을 때.
#include <stdint.h>
#include <string.h>
#define BASE (0x68u * 0x2000u)
#define SIZE 0x40000u
uint8_t *g_sys, *g_cd, *g_cpu;  // SysCardRAM · CDRAM · HuCPU 객체(+0x24 PC · +0x40 MPR[9] · +0x70 마지막 논리 읽기 주소)
void *g_opsite;
uint8_t cov[SIZE];
uint8_t pages[0x20];            // 뱅크마다 — 명령을 인출할 때 걸려 있던 논리 쪽(비트 = 쪽 번호)
uint8_t mprs[0x20][32][8];      // 뱅크마다 — 그 뱅크에서 명령을 인출할 때의 MPR 8칸 조합(최대 32가지)
uint8_t nmpr[0x20];
uint8_t cov_read(uint32_t A) {
    uint32_t i = A - BASE;
    if (__builtin_return_address(0) == g_opsite) {
        cov[i] |= 1;
        unsigned b = i >> 13;
        pages[b] |= 1u << ((*(uint32_t *)(g_cpu + 0x70) >> 13) & 7);
        const uint8_t *m = g_cpu + 0x40;
        int n = nmpr[b], k;
        for (k = 0; k < n; k++) if (!memcmp(mprs[b][k], m, 8)) break;
        if (k == n && n < 32) { memcpy(mprs[b][n], m, 8); nmpr[b]++; }
    } else if ((*(uint32_t *)(g_cpu + 0x70) & 0xFFFF) == (*(uint32_t *)(g_cpu + 0x24) & 0xFFFF))
        cov[i] |= 8;
    else
        cov[i] |= 2;
    return i < 0x30000u ? g_sys[i] : g_cd[i - 0x30000u];
}
void cov_write(uint32_t A, uint8_t V) {
    uint32_t i = A - BASE;
    cov[i] |= 4;
    if (i < 0x30000u) g_sys[i] = V; else g_cd[i - 0x30000u] = V;
}
