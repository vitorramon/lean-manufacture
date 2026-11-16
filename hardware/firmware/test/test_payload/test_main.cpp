// Payloads e tópicos do firmware comparados, byte a byte, às mensagens de referência do contrato
// (pipeline/contrato/exemplos/validos, convertidas em JSON compacto por scripts/gerar_referencias.py).
#include <math.h>
#include <string.h>
#include <unity.h>

#include "payload.h"
#include "referencias_contrato.h"
#include "sequencia.h"

using namespace logica;

static const ReferenciaContrato& ref(const char* nome) {
    for (unsigned i = 0; i < N_REFERENCIAS; ++i) {
        if (strcmp(REFERENCIAS[i].nome, nome) == 0) return REFERENCIAS[i];
    }
    TEST_FAIL_MESSAGE(nome);
    return REFERENCIAS[0];
}

static char buf[TAMANHO_MAX_PAYLOAD + 1];
static char topico[128];

void setUp() { memset(buf, 0, sizeof buf); memset(topico, 0, sizeof topico); }
void tearDown() {}

void test_referencias_carregadas() {
    TEST_ASSERT_TRUE_MESSAGE(N_REFERENCIAS >= 10, "mensagens de referência do contrato não geradas");
}

void test_evt_ciclo_inicio_igual_referencia() {
    const auto& r = ref("evt-ciclo-inicio");
    EventoCiclo e{Fase::Inicio, 787600, 0};
    TEST_ASSERT_GREATER_THAN(0, payloadCiclo(buf, sizeof buf, 42, 3, e));
    TEST_ASSERT_EQUAL_STRING(r.payload, buf);
    TEST_ASSERT_GREATER_THAN(0, topicoEvt(topico, sizeof topico, "esp32-bat01", "ciclo"));
    TEST_ASSERT_EQUAL_STRING(r.topico, topico);
}

void test_evt_ciclo_fim_igual_referencia() {
    const auto& r = ref("evt-ciclo-fim");
    EventoCiclo e{Fase::Fim, 815020, 815020 - 787600};  // 27420 ms = 27.42 s
    TEST_ASSERT_GREATER_THAN(0, payloadCiclo(buf, sizeof buf, 43, 3, e));
    TEST_ASSERT_EQUAL_STRING(r.payload, buf);
}

void test_ciclo_da_maquina_gera_referencias() {
    // A máquina de estados, alimentada com os instantes das referências, produz as duas mensagens.
    MaquinaCiclo m;
    Sequencia s(42);
    EventoCiclo e1 = m.tocar(787600);
    payloadCiclo(buf, sizeof buf, s.proximo(), 3, e1);
    TEST_ASSERT_EQUAL_STRING(ref("evt-ciclo-inicio").payload, buf);
    EventoCiclo e2 = m.tocar(815020);
    payloadCiclo(buf, sizeof buf, s.proximo(), 3, e2);
    TEST_ASSERT_EQUAL_STRING(ref("evt-ciclo-fim").payload, buf);
}

void test_tel_igual_referencia() {
    const auto& r = ref("tel-temperatura-com-boot");
    TEST_ASSERT_GREATER_THAN(0, payloadTel(buf, sizeof buf, 41, 812345, 3, 24.6f));
    TEST_ASSERT_EQUAL_STRING(r.payload, buf);
    topicoTel(topico, sizeof topico, "esp32-bat01", "temperatura");
    TEST_ASSERT_EQUAL_STRING(r.topico, topico);
}

void test_tel_arredonda_resolucao_do_sensor() {
    payloadTel(buf, sizeof buf, 41, 812345, 3, 24.6400003f);
    TEST_ASSERT_EQUAL_STRING(ref("tel-temperatura-com-boot").payload, buf);
}

void test_tel_nan_nao_publica() {
    // payload-nan.json é inválido no contrato: o firmware nunca o monta.
    TEST_ASSERT_EQUAL(0, payloadTel(buf, sizeof buf, 1, 1, 1, NAN));
    TEST_ASSERT_EQUAL(0, payloadTel(buf, sizeof buf, 1, 1, 1, INFINITY));
}

void test_status_online_igual_referencia() {
    const auto& r = ref("status-online-hardware");
    TEST_ASSERT_GREATER_THAN(0, payloadStatusOnline(buf, sizeof buf, "1.0.0", 12, "hardware"));
    TEST_ASSERT_EQUAL_STRING(r.payload, buf);
    topicoStatus(topico, sizeof topico, "esp32-bat01");
    TEST_ASSERT_EQUAL_STRING(r.topico, topico);

    payloadStatusOnline(buf, sizeof buf, "1.0.0", 7, "firmware:emulado");
    TEST_ASSERT_EQUAL_STRING(ref("status-online-firmware-emulado").payload, buf);
}

void test_last_will_igual_referencia() {
    TEST_ASSERT_GREATER_THAN(0, payloadLastWill(buf, sizeof buf));
    TEST_ASSERT_EQUAL_STRING(ref("status-offline-last-will").payload, buf);
}

void test_teto_de_32_bits() {
    // up_ms no teto do millis(): o firmware publica sem estourar (referência up-ms-teto-millis, sem boot).
    payloadTel(buf, sizeof buf, 4294967295u, 4294967295u, 0, 24.6f);
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"seq\":4294967295"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"up_ms\":4294967295"));
}

void test_sem_data_hora_nem_campo_extra() {
    const char* proibidas[] = {"\"ts\"", "timestamp", "\"time\"", "\"date\"", "\"data\"", "\"hora\"",
                               "epoch", "peca", "unidade"};
    EventoCiclo ini{Fase::Inicio, 1000, 0};
    EventoCiclo fim{Fase::Fim, 28000, 27000};
    char saidas[4][256];
    payloadCiclo(saidas[0], 256, 0, 1, ini);
    payloadCiclo(saidas[1], 256, 1, 1, fim);
    payloadTel(saidas[2], 256, 2, 30000, 1, 25.0f);
    payloadStatusOnline(saidas[3], 256, "0.1.0", 1, "hardware");
    for (auto& s : saidas) {
        for (const char* p : proibidas) {
            TEST_ASSERT_NULL_MESSAGE(strstr(s, p), s);
        }
    }
}

void test_fim_com_duracao_zero_nao_publica() {
    EventoCiclo e{Fase::Fim, 1000, 0};
    TEST_ASSERT_EQUAL(0, payloadCiclo(buf, sizeof buf, 1, 1, e));
}

void test_buffer_pequeno_nao_publica_truncado() {
    char pequeno[10];
    TEST_ASSERT_EQUAL(0, payloadStatusOnline(pequeno, sizeof pequeno, "0.1.0", 1, "hardware"));
    TEST_ASSERT_EQUAL(0, topicoStatus(pequeno, sizeof pequeno, "esp32-bat01"));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_referencias_carregadas);
    RUN_TEST(test_evt_ciclo_inicio_igual_referencia);
    RUN_TEST(test_evt_ciclo_fim_igual_referencia);
    RUN_TEST(test_ciclo_da_maquina_gera_referencias);
    RUN_TEST(test_tel_igual_referencia);
    RUN_TEST(test_tel_arredonda_resolucao_do_sensor);
    RUN_TEST(test_tel_nan_nao_publica);
    RUN_TEST(test_status_online_igual_referencia);
    RUN_TEST(test_last_will_igual_referencia);
    RUN_TEST(test_teto_de_32_bits);
    RUN_TEST(test_sem_data_hora_nem_campo_extra);
    RUN_TEST(test_fim_com_duracao_zero_nao_publica);
    RUN_TEST(test_buffer_pequeno_nao_publica_truncado);
    return UNITY_END();
}
