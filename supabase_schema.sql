-- ====================================================================
-- Script SQL para Criação das Tabelas do RemoteXPTI no Supabase
-- Copie e cole este script no SQL Editor do seu projeto Supabase
-- ====================================================================

-- 1. Tabela de Servidores RDP Sincronizados
CREATE TABLE IF NOT EXISTS public.servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER DEFAULT 3389,
    username TEXT,
    "group" TEXT DEFAULT 'Geral',
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    favorite BOOLEAN DEFAULT FALSE,
    admin_mode BOOLEAN DEFAULT FALSE,
    multimon BOOLEAN DEFAULT FALSE,
    fullscreen BOOLEAN DEFAULT TRUE,
    notes TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Habilita Row Level Security (RLS) para proteção
ALTER TABLE public.servers ENABLE ROW LEVEL SECURITY;

-- 3. Políticas de Acesso
-- Leitura pública para clientes (permite que qualquer app RemoteXPTI com a chave anon leia a lista)
CREATE POLICY "Permitir leitura anonima de servidores" 
ON public.servers FOR SELECT 
USING (true);

-- Inserção e Atualização (Upsert)
CREATE POLICY "Permitir upsert de servidores" 
ON public.servers FOR ALL 
USING (true)
WITH CHECK (true);

-- 4. Tabela de Configurações Globais / Canais (Opcional)
CREATE TABLE IF NOT EXISTS public.app_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.app_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Permitir leitura de app_config" 
ON public.app_config FOR SELECT 
USING (true);

-- Valores iniciais recomendados
INSERT INTO public.app_config (key, value)
VALUES 
    ('public_beta_version', '"1.1.0"'),
    ('broadcast_message', '""'),
    ('min_required_version', '"1.0.35"')
ON CONFLICT (key) DO NOTHING;
