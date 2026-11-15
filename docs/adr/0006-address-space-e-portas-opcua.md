# ADR-0006: Um servidor OPC UA, vários objetos; portas 4850 e 4851

- Estado: Proposto
- Data: 2026-11-15
- Origem: aula M3.A2; colisão de portas com o Virtual-Factory

## Contexto

A aula 2 do M3 determina: um servidor OPC UA, um objeto por dispositivo, hierarquia que espelha a planta; criar um
servidor por dispositivo é o "erro comum". A disciplina convenciona a porta 4840 para os dispositivos e 4841 para o
servidor T2T do gêmeo. No Virtual-Factory, 4840 é o servidor OPC UA do CLP virtual e 4841 é o backplane entre o CLP
e seu módulo de comunicação.

## Decisão

1. `device-gateway` serve `opc.tcp://0.0.0.0:4850/lean/dispositivos`.
2. `twin-t2t` serve `opc.tcp://0.0.0.0:4851`.
3. Address space dos dispositivos: `Objects/LinhaCelulares/<Dispositivo>/<Variavel>`, com identificadores de texto
   determinísticos, por exemplo `ns=2;s=LinhaCelulares.Bateria_01.TempoCiclo`.
4. Todo objeto de dispositivo tem `Online` e `UltimaLeitura`, além das suas variáveis de processo.
5. `LinhaCelulares.Rastreio` reúne `UltimaPeca`, `LeadTimeReal` e `PecasConcluidas`.
6. Os objetos são criados a partir de `config/dispositivos.yaml`. Acrescentar um dispositivo é acrescentar uma
   entrada nesse arquivo.
7. Segurança: sem criptografia e acesso anônimo, como nas aulas.
8. As portas e os nós constam do cartão de conexão.

## Consequências

- Atende ao critério da aula e permite a evidência "print do address space com ≥ 2 objetos".
- As aulas Extras já determinam uma porta T2T por gêmeo (4841, 4842, 4843, coordenador em 4844), sempre
  registrada no cartão de conexão; usar 4851 não é desvio. Ainda assim, quem assumir 4841 na nossa máquina
  encontrará o backplane do CLP, que não é OPC UA.
- Servidor sem autenticação só é aceitável em rede de laboratório; registrar como limitação.

## Alternativas consideradas

- **Mover as portas da base** para liberar 4840 e 4841: exigiria alterar o Virtual-Factory, contra o ADR-0001.
- **Acrescentar os dispositivos ao servidor OPC UA do CLP da base**: um só servidor para tudo, porém esse address
  space é gerado a partir dos modelos da simulação e não é nosso para estender.
- **Um servidor por dispositivo**: o erro que a aula aponta.
