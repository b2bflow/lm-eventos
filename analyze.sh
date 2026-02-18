#!/bin/bash
echo "🔍 Iniciando análise estática..."
echo ""

# Criar pasta reports se não existir
mkdir -p reports

echo "📊 Pylint (JSON)..."
pylint agents/ clients/ services/ repositories/ tools/ mixins/ utils/ workers/ container/ controllers/ database/ interfaces/ \
  --disable=C0114,C0115,C0116,C0301,C0411,C0412,C0413,W0718,W3101 \
  --load-plugins=pylint_mongoengine \
  --output-format=json > reports/pylint_report.json
echo ""
echo "🔬 MyPy..."
mypy agents/ clients/ services/ repositories/ tools/ mixins/ utils/ workers/ container/ controllers/ database/ interfaces/ > reports/mypy_report.txt 2>&1
echo ""
echo "✅ Análise concluída!"
echo ""
echo "📁 Relatórios salvos em:"
echo "   - reports/pylint_report.json"
echo "   - reports/mypy_report.txt"