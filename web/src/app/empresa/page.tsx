import { redirect } from 'next/navigation'

/** A lista de empresas e catálogos é a raiz (`/`) desde a E4; este caminho só redireciona. */
export default function EmpresaPage() {
  redirect('/')
}
