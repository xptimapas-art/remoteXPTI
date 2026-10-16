export async function toggleServerFavorite(serverId: string): Promise<boolean> {
  const response = await fetch(`/api/servers/${encodeURIComponent(serverId)}/favorite`, {
    method: 'POST', signal: AbortSignal.timeout(15000),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Não foi possível salvar o favorito.');
  }
  if (data.status !== 'ok' || typeof data.favorite !== 'boolean') {
    throw new Error('O aplicativo não confirmou o salvamento do favorito. Atualize a lista e tente novamente.');
  }
  return data.favorite;
}
