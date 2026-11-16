// `seq` (um contador para tel e evt, recomeça a cada boot) e `boot` persistido.
#include <string.h>
#include <unity.h>

#include "payload.h"
#include "sequencia.h"

using namespace logica;

class ArmazenamentoMemoria : public ArmazenamentoBoot {
public:
    bool tem = false;
    uint32_t valor = 0;
    bool falhar_gravacao = false;
    bool ler(uint32_t& v) override {
        if (!tem) return false;
        v = valor;
        return true;
    }
    bool gravar(uint32_t v) override {
        if (falhar_gravacao) return false;
        tem = true;
        valor = v;
        return true;
    }
};

void setUp() {}
void tearDown() {}

void test_seq_comeca_em_zero_e_cresce() {
    Sequencia s;
    TEST_ASSERT_EQUAL_UINT32(0, s.proximo());
    TEST_ASSERT_EQUAL_UINT32(1, s.proximo());
    TEST_ASSERT_EQUAL_UINT32(2, s.espiar());
}

void test_seq_unico_para_tel_e_evt() {
    // Intercala telemetria e eventos: os seq saem 0,1,2,3 sem repetir entre tópicos.
    Sequencia s;
    char buf[256];
    EventoCiclo ini{Fase::Inicio, 100, 0};
    EventoCiclo fim{Fase::Fim, 2100, 2000};
    payloadTel(buf, sizeof buf, s.proximo(), 50, 1, 25.0f);
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"seq\":0,"));
    payloadCiclo(buf, sizeof buf, s.proximo(), 1, ini);
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"seq\":1,"));
    payloadTel(buf, sizeof buf, s.proximo(), 1050, 1, 25.1f);
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"seq\":2,"));
    payloadCiclo(buf, sizeof buf, s.proximo(), 1, fim);
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"seq\":3,"));
}

void test_seq_da_volta_em_2_32() {
    Sequencia s(4294967295u);
    TEST_ASSERT_EQUAL_UINT32(4294967295u, s.proximo());
    TEST_ASSERT_EQUAL_UINT32(0, s.proximo());
}

void test_primeiro_boot_e_1_e_persiste() {
    ArmazenamentoMemoria a;
    TEST_ASSERT_EQUAL_UINT32(1, registrarBoot(a));
    TEST_ASSERT_TRUE(a.tem);
    TEST_ASSERT_EQUAL_UINT32(1, a.valor);
}

void test_boot_incrementa_a_cada_inicializacao() {
    ArmazenamentoMemoria a;
    for (uint32_t i = 1; i <= 5; ++i) TEST_ASSERT_EQUAL_UINT32(i, registrarBoot(a));
    TEST_ASSERT_EQUAL_UINT32(5, a.valor);
}

void test_boot_continua_do_valor_gravado() {
    ArmazenamentoMemoria a;
    a.tem = true;
    a.valor = 11;
    TEST_ASSERT_EQUAL_UINT32(12, registrarBoot(a));  // como em status-online-hardware (boot 12)
}

void test_falha_de_gravacao_ainda_devolve_boot() {
    ArmazenamentoMemoria a;
    a.tem = true;
    a.valor = 3;
    a.falhar_gravacao = true;
    TEST_ASSERT_EQUAL_UINT32(4, registrarBoot(a));
    TEST_ASSERT_EQUAL_UINT32(3, a.valor);
}

void test_novo_boot_reinicia_seq() {
    // Simula dois boots: o par (boot, seq) distingue o seq 0 de cada um.
    ArmazenamentoMemoria a;
    char p1[128], p2[128];
    uint32_t b1 = registrarBoot(a);
    Sequencia s1;
    s1.proximo();
    payloadTel(p1, sizeof p1, s1.proximo(), 10, b1, 24.0f);
    uint32_t b2 = registrarBoot(a);
    Sequencia s2;
    s2.proximo();
    payloadTel(p2, sizeof p2, s2.proximo(), 10, b2, 24.0f);
    TEST_ASSERT_EQUAL_STRING("{\"seq\":1,\"up_ms\":10,\"boot\":1,\"v\":24}", p1);
    TEST_ASSERT_EQUAL_STRING("{\"seq\":1,\"up_ms\":10,\"boot\":2,\"v\":24}", p2);
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_seq_comeca_em_zero_e_cresce);
    RUN_TEST(test_seq_unico_para_tel_e_evt);
    RUN_TEST(test_seq_da_volta_em_2_32);
    RUN_TEST(test_primeiro_boot_e_1_e_persiste);
    RUN_TEST(test_boot_incrementa_a_cada_inicializacao);
    RUN_TEST(test_boot_continua_do_valor_gravado);
    RUN_TEST(test_falha_de_gravacao_ainda_devolve_boot);
    RUN_TEST(test_novo_boot_reinicia_seq);
    return UNITY_END();
}
