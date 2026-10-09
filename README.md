# Minha Lenda · executor de entregas

Este repositório só contém o **executor** que monta os livros já pagos (texto pelo motor do site, ilustrações, PDF A5, audiolivro) e o workflow do GitHub Actions que o roda. O motor, os prompts e os dados ficam no Worker da Cloudflare, fora daqui.

- `entrega/entrega.py`: produz e entrega os pedidos da fila (`/admin/api/pedidos?status=fila`).
- `.github/workflows/entrega.yml`: roda quando o site confirma um pagamento (`repository_dispatch`) e a cada 20 min como reserva.
- Sem segredos no GitHub: o workflow se identifica ao site com o token OIDC do próprio GitHub Actions, e a narração passa pelo site (a chave do Gemini não sai da Cloudflare).
- O log é público: o executor não imprime nome de criança, título nem link de entrega.

Fontes Alegreya e UnifrakturMaguntia sob a SIL Open Font License.
