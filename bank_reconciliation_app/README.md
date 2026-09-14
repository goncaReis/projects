# Reconciliações bancárias

Aplicação Streamlit para conciliar movimentos contabilísticos com extratos bancários, por correspondência automática ou seleção manual.

## Instalação e execução

```text
python -m pip install -r requirements.txt
streamlit run reconciliacoes.py
```

## Começar e continuar um trabalho

1. Carregue um ficheiro `.xlsx` ou `.xls` com as folhas `CNT` e `BANCO`. Ambas devem conter `Data`, `Descrição` e `Valor`. Pode incluir outras colunas, diferentes em cada folha. Existe um modelo em `file/template.xlsx`.
2. Para um ficheiro novo, indique os saldos iniciais e os limites de correspondência. A reconciliação automática considera valores iguais, proximidade das datas e semelhança das descrições. Depois pode selecionar movimentos em **Manual**, incluindo combinações de vários movimentos.
3. Consulte as reconciliações em **Conciliados** e selecione **Remover** para devolver os movimentos aos pendentes. A anulação fica registada em **Histórico**.
4. Use **Preparar ficheiro download**, disponível em todas as vistas, e descarregue `reconciliacao.xlsx`. Pode guardar mesmo sem fazer novas reconciliações ou quando não existem movimentos pendentes.
5. Na próxima sessão, carregue o ficheiro descarregado. Os saldos, definições, reconciliações e histórico são recuperados. O estado guardado é retomado sem executar novamente a reconciliação automática sobre os pendentes.

O trabalho fica guardado no ficheiro que descarregar. Não existe gravação automática no servidor. Para acrescentar movimentos, adicione linhas a `CNT` ou `BANCO` no ficheiro guardado, deixando a identificação técnica das novas linhas em branco. Também pode acrescentar colunas. Depois de reabrir, os novos movimentos ficam disponíveis para conciliação manual.

Em **Manual**, use **Pesquisar na coluna** para escolher onde procurar o termo, separadamente na contabilidade e no banco. A coluna inicial é `Descrição`; pode escolher qualquer outra coluna apresentada, incluindo as adicionais. Escreva o termo e clique em **Atualizar** do lado respetivo. A pesquisa ignora maiúsculas/minúsculas e aceita vários termos separados por `;` (basta encontrar um deles). Os filtros de datas e valores continuam a aplicar-se.

### Combinações possíveis

Ative **Mostrar apenas quando existe uma combinação** para apresentar apenas correspondências sem alternativas dentro da pesquisa realizada. Em **Por documento**, a contagem é feita separadamente para cada movimento selecionado. Em **Por total**, aplica-se ao total selecionado. Todos os períodos pesquisados entram na contagem: duas alternativas em dias diferentes continuam a ser duas possibilidades. Uma combinação única pode conter vários movimentos.

A tabela não apresenta os identificadores técnicos dos movimentos. A coluna **Opção** distingue as alternativas apresentadas. O toggle apenas filtra as propostas; a conciliação continua a depender da seleção e confirmação do utilizador.

### Notas e regras por cliente

Na secção **Cliente e regras de reconciliação** da página **Manual**:

1. Escolha **Novo cliente**, indique o nome e escreva as suas regras ou notas.
2. Clique em **Guardar notas**.
3. Noutra sessão, selecione o cliente na lista para consultar ou editar as notas. Volte a clicar em **Guardar notas** para persistir alterações.

O ficheiro `file/client_notes.csv` é criado na primeira gravação. Guarda um bloco de notas por cliente, com a última data de atualização em UTC. Suporta acentos, quebras de linha, vírgulas e ponto e vírgula. Editar as notas de um cliente mantém as notas dos outros clientes.

As notas ficam no computador ou servidor onde a aplicação está a correr e são independentes do Excel de reconciliação. Num alojamento com disco temporário, esta pasta precisa de armazenamento persistente. O CSV não é incluído no controlo de versões. As regras servem de consulta e não são executadas automaticamente pelo algoritmo.

## Conteúdo do ficheiro guardado

| Folha | Conteúdo |
| --- | --- |
| `CNT` / `BANCO` | Movimentos pendentes, com as colunas originais e uma identificação persistente por movimento. |
| `MATCH CNT` / `MATCH BANCO` | Movimentos conciliados, incluindo os anteriores, com identificação, número de reconciliação e nota. |
| `HISTORICO` | Criações e anulações, com data/hora UTC, número de reconciliação, identificação dos movimentos e notas. Um evento pode abranger várias linhas. |
| `CONFIGURACAO` | Saldos iniciais, limites de correspondência, próximo ID e informação necessária para reabrir o ficheiro. |

Os IDs das reconciliações são iguais na aplicação e no Excel. Cada nova reconciliação usa o próximo ID disponível. Um ID anulado não é reutilizado. Seleções vazias ou inválidas não consomem IDs.

Ficheiros antigos com `MATCH CNT` e `MATCH BANCO` também são aceites. O próximo ID é superior ao maior número encontrado nas duas folhas. As reconciliações anteriores aparecem em **Conciliados** e recebem eventos `Importada` no histórico, com a data da importação. A data original de criação e anulações anteriores não podem ser recuperadas se não existirem no ficheiro antigo.

Não apague nem altere as identificações técnicas ou as folhas `HISTORICO` e `CONFIGURACAO`. Ao copiar uma linha para acrescentar um novo movimento, deixe a identificação técnica em branco para receber um novo ID.

## Preservação dos dados

- Os valores e a ordem das colunas originais são preservados na exportação, incluindo colunas opcionais vazias, descrições com pontuação, referências textuais com zeros iniciais e textos como `NA`.
- A preparação das datas, valores e descrições para comparação não substitui os dados originais. As tabelas da aplicação permitem selecionar movimentos; as colunas de origem são apenas de leitura.
- Colunas do utilizador com nomes utilizados pela aplicação, como `Ver`, `ordem`, `nota` ou `index`, são preservadas. Na interface podem receber o sufixo `(original)`; na exportação mantêm o nome original. Os campos técnicos recebem nomes alternativos quando necessário.
- A preservação aplica-se aos dados das folhas de movimentos. Formatação, fórmulas, gráficos, macros e folhas alheias à reconciliação não são preservados. Fórmulas são lidas pelos valores calculados guardados no Excel. Zeros apresentados apenas por formatação numérica não são identificadores textuais.

## Verificação

```text
python -m unittest -v test_reconciliation_workspace test_reconciliation_app test_client_features
```

Os testes cobrem ciclos de gravação e reabertura, compatibilidade com ficheiros antigos, IDs, anulações, preservação de colunas e referências, exportações vazias, seleção do candidato bancário e utilização das vistas da aplicação.
