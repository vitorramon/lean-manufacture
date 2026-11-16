// Debounce e máquina de estados do ciclo, com tempo simulado (sem placa, sem delay()).
#include <unity.h>

#include "ciclo.h"
#include "debounce.h"

using namespace logica;

void setUp() {}
void tearDown() {}

static const uint32_t JANELA = 30;

void test_toque_limpo_confirma_apos_janela_com_instante_da_borda() {
    Debounce d(JANELA);
    uint32_t inst = 0;
    TEST_ASSERT_FALSE(d.atualizar(true, 1000, inst));
    TEST_ASSERT_FALSE(d.atualizar(true, 1029, inst));
    TEST_ASSERT_TRUE(d.atualizar(true, 1030, inst));
    TEST_ASSERT_TRUE(d.estavel());
    TEST_ASSERT_EQUAL_UINT32(1000, inst);
    TEST_ASSERT_FALSE(d.atualizar(true, 1100, inst));  // segue pressionado: nada novo
}

void test_repique_nao_gera_toques_extras() {
    // Contato que vibra 5 ms durante 20 ms e depois firma: um único toque.
    Debounce d(JANELA);
    uint32_t inst = 0;
    int mudancas = 0;
    bool nivel = false;
    for (uint32_t t = 0; t < 20; ++t) {
        if (t % 5 == 0) nivel = !nivel;
        if (d.atualizar(nivel, 1000 + t, inst)) ++mudancas;
    }
    for (uint32_t t = 20; t < 200; ++t) {
        if (d.atualizar(true, 1000 + t, inst)) ++mudancas;
    }
    TEST_ASSERT_EQUAL_INT(1, mudancas);
    TEST_ASSERT_TRUE(d.estavel());
}

void test_pulso_curto_e_ignorado() {
    Debounce d(JANELA);
    uint32_t inst = 0;
    for (uint32_t t = 0; t < 20; ++t) TEST_ASSERT_FALSE(d.atualizar(true, t, inst));
    for (uint32_t t = 20; t < 200; ++t) TEST_ASSERT_FALSE(d.atualizar(false, t, inst));
    TEST_ASSERT_FALSE(d.estavel());
}

void test_volta_do_millis() {
    Debounce d(JANELA);
    uint32_t inst = 0;
    const uint32_t perto = 0xFFFFFFF0u;
    TEST_ASSERT_FALSE(d.atualizar(true, perto, inst));
    TEST_ASSERT_FALSE(d.atualizar(true, perto + 10, inst));
    TEST_ASSERT_TRUE(d.atualizar(true, perto + JANELA, inst));  // passou de 2^32 e voltou
    TEST_ASSERT_EQUAL_UINT32(perto, inst);
}

// Mantém o nível por [de, ate) ms, amostrando a cada 1 ms; devolve quantos eventos saíram.
static int segurar(BotaoCiclo& b, bool nivel, uint32_t de, uint32_t ate, EventoCiclo* ultimo) {
    int n = 0;
    EventoCiclo e{};
    for (uint32_t t = de; t < ate; ++t) {
        if (b.amostrar(nivel, t, e)) {
            ++n;
            if (ultimo) *ultimo = e;
        }
    }
    return n;
}

void test_botao_inicio_e_fim_com_duracao() {
    BotaoCiclo b(JANELA);
    EventoCiclo e{};
    TEST_ASSERT_EQUAL_INT(0, segurar(b, false, 0, 1000, &e));
    TEST_ASSERT_EQUAL_INT(1, segurar(b, true, 1000, 1200, &e));  // aperta
    TEST_ASSERT_TRUE(e.fase == Fase::Inicio);
    TEST_ASSERT_EQUAL_UINT32(1000, e.up_ms);
    TEST_ASSERT_TRUE(b.cicloAberto());
    TEST_ASSERT_EQUAL_INT(0, segurar(b, false, 1200, 28420, &e));  // solta: soltar não gera evento
    TEST_ASSERT_EQUAL_INT(1, segurar(b, true, 28420, 28600, &e));  // aperta de novo
    TEST_ASSERT_TRUE(e.fase == Fase::Fim);
    TEST_ASSERT_EQUAL_UINT32(28420, e.up_ms);
    TEST_ASSERT_EQUAL_UINT32(27420, e.dur_ms);
    TEST_ASSERT_FALSE(b.cicloAberto());
}

void test_botao_com_repique_conta_um_ciclo() {
    BotaoCiclo b(JANELA);
    EventoCiclo e{};
    int eventos = 0;
    // aperto com repique
    eventos += segurar(b, true, 0, 3, &e);
    eventos += segurar(b, false, 3, 6, &e);
    eventos += segurar(b, true, 6, 9, &e);
    eventos += segurar(b, false, 9, 11, &e);
    eventos += segurar(b, true, 11, 300, &e);
    // soltura com repique
    eventos += segurar(b, false, 300, 303, &e);
    eventos += segurar(b, true, 303, 305, &e);
    eventos += segurar(b, false, 305, 5000, &e);
    TEST_ASSERT_EQUAL_INT(1, eventos);
    TEST_ASSERT_TRUE(e.fase == Fase::Inicio);
    TEST_ASSERT_EQUAL_UINT32(11, e.up_ms);  // borda que firmou
}

void test_maquina_duracao_atravessa_volta_do_millis() {
    MaquinaCiclo m;
    m.tocar(0xFFFFF000u);
    EventoCiclo fim = m.tocar(0x00001000u);
    TEST_ASSERT_TRUE(fim.fase == Fase::Fim);
    TEST_ASSERT_EQUAL_UINT32(0x2000u, fim.dur_ms);
}

void test_maquina_alterna_varios_ciclos() {
    MaquinaCiclo m;
    for (uint32_t i = 0; i < 5; ++i) {
        TEST_ASSERT_TRUE(m.tocar(i * 1000).fase == Fase::Inicio);
        EventoCiclo f = m.tocar(i * 1000 + 500);
        TEST_ASSERT_TRUE(f.fase == Fase::Fim);
        TEST_ASSERT_EQUAL_UINT32(500, f.dur_ms);
    }
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_toque_limpo_confirma_apos_janela_com_instante_da_borda);
    RUN_TEST(test_repique_nao_gera_toques_extras);
    RUN_TEST(test_pulso_curto_e_ignorado);
    RUN_TEST(test_volta_do_millis);
    RUN_TEST(test_botao_inicio_e_fim_com_duracao);
    RUN_TEST(test_botao_com_repique_conta_um_ciclo);
    RUN_TEST(test_maquina_duracao_atravessa_volta_do_millis);
    RUN_TEST(test_maquina_alterna_varios_ciclos);
    return UNITY_END();
}
