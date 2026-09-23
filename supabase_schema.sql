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
    password TEXT,
    "group" TEXT DEFAULT 'Geral',
    scope TEXT DEFAULT 'corporate',
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
DROP POLICY IF EXISTS "Permitir leitura anonima de servidores" ON public.servers;
CREATE POLICY "Permitir leitura anonima de servidores" 
ON public.servers FOR SELECT 
USING (true);

DROP POLICY IF EXISTS "Permitir upsert de servidores" ON public.servers;
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

DROP POLICY IF EXISTS "Permitir leitura de app_config" ON public.app_config;
CREATE POLICY "Permitir leitura de app_config" 
ON public.app_config FOR SELECT 
USING (true);

-- Valores iniciais recomendados
INSERT INTO public.app_config (key, value)
VALUES 
    ('public_beta_version', '"1.6.4"'),
    ('broadcast_message', '""'),
    ('min_required_version', '"1.0.35"')
ON CONFLICT (key) DO NOTHING;

-- 5. Tabela de Telemetria Consolidada das ONUs Ajin (Jurerê Internacional)
CREATE TABLE IF NOT EXISTS public.ajin_telemetry (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    total_onus INTEGER DEFAULT 0,
    online_count INTEGER DEFAULT 0,
    offline_count INTEGER DEFAULT 0,
    unregistered_count INTEGER DEFAULT 0,
    availability_pct NUMERIC(5, 2) DEFAULT 0.0,
    data JSONB NOT NULL DEFAULT '[]'::jsonb,
    unregistered_onus JSONB DEFAULT '[]'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.ajin_telemetry ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Permitir leitura publica de ajin_telemetry" ON public.ajin_telemetry;
CREATE POLICY "Permitir leitura publica de ajin_telemetry" 
ON public.ajin_telemetry FOR SELECT 
USING (true);

DROP POLICY IF EXISTS "Permitir escrita de ajin_telemetry" ON public.ajin_telemetry;
CREATE POLICY "Permitir escrita de ajin_telemetry" 
ON public.ajin_telemetry FOR ALL 
USING (true)
WITH CHECK (true);

-- 6. Tabela de Rótulos e Nomes Personalizados de ONUs Ajin
CREATE TABLE IF NOT EXISTS public.ajin_labels (
    port TEXT NOT NULL,
    onu_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    PRIMARY KEY (port, onu_id)
);

ALTER TABLE public.ajin_labels ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Permitir leitura publica de ajin_labels" ON public.ajin_labels;
CREATE POLICY "Permitir leitura publica de ajin_labels" 
ON public.ajin_labels FOR SELECT 
USING (true);

DROP POLICY IF EXISTS "Permitir escrita de ajin_labels" ON public.ajin_labels;
CREATE POLICY "Permitir escrita de ajin_labels" 
ON public.ajin_labels FOR ALL 
USING (true)
WITH CHECK (true);
