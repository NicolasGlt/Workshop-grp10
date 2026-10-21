BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE utilisateurs (
    id_user UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prenom VARCHAR(100) NOT NULL,
    nom VARCHAR(100) NOT NULL,
    creation_user TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE comptes (
    id_compte UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_user UUID NOT NULL REFERENCES utilisateurs(id_user) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL UNIQUE,
    numero_tel VARCHAR(30),
    password_hash TEXT NOT NULL,
    adresse TEXT,
    statut VARCHAR(30) NOT NULL DEFAULT 'ACTIVE'
        CHECK (statut IN ('ACTIVE', 'BLOCKED', 'DISABLED')),
    creation_compte TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE comptes_bancaires (
    id_compte_bancaire UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_compte UUID NOT NULL REFERENCES comptes(id_compte) ON DELETE CASCADE,
    iban_reference VARCHAR(100) UNIQUE,
    solde NUMERIC(15,2) NOT NULL DEFAULT 0.00 CHECK (solde >= 0),
    devise CHAR(3) NOT NULL DEFAULT 'EUR',
    actif BOOLEAN NOT NULL DEFAULT TRUE,
    creation_compte_bancaire TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cartes (
    id_carte UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_compte_bancaire UUID NOT NULL REFERENCES comptes_bancaires(id_compte_bancaire) ON DELETE CASCADE,
    card_token VARCHAR(255) NOT NULL UNIQUE,
    card_last4 CHAR(4) NOT NULL CHECK (card_last4 ~ '^[0-9]{4}$'),
    numero_carte_hash TEXT,
    nom_carte_hash TEXT,
    expiration_hash TEXT,
    actif BOOLEAN NOT NULL DEFAULT TRUE,
    creation_carte TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE transactions (
    id_transaction UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_compte_emetteur UUID NOT NULL REFERENCES comptes_bancaires(id_compte_bancaire),
    id_compte_recepteur UUID NOT NULL REFERENCES comptes_bancaires(id_compte_bancaire),
    id_carte UUID REFERENCES cartes(id_carte) ON DELETE SET NULL,
    montant NUMERIC(15,2) NOT NULL CHECK (montant > 0),
    devise CHAR(3) NOT NULL DEFAULT 'EUR',
    statut VARCHAR(30) NOT NULL DEFAULT 'PENDING'
        CHECK (statut IN ('PENDING','AUTHORIZED','REJECTED','COMPLETED','FAILED')),
    reference_banque VARCHAR(255),
    description VARCHAR(500),
    date_transaction TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (id_compte_emetteur <> id_compte_recepteur)
);

CREATE TABLE logs (
    id_log UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_compte UUID REFERENCES comptes(id_compte) ON DELETE SET NULL,
    id_transaction UUID REFERENCES transactions(id_transaction) ON DELETE SET NULL,
    type_event VARCHAR(100) NOT NULL,
    niveau VARCHAR(20) NOT NULL DEFAULT 'INFO',
    adresse_ip INET,
    description TEXT,
    date_log TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_comptes_email ON comptes(email);
CREATE INDEX idx_comptes_user ON comptes(id_user);
CREATE INDEX idx_bancaires_compte ON comptes_bancaires(id_compte);
CREATE INDEX idx_cartes_bancaire ON cartes(id_compte_bancaire);
CREATE INDEX idx_transactions_emetteur ON transactions(id_compte_emetteur);
CREATE INDEX idx_transactions_recepteur ON transactions(id_compte_recepteur);
CREATE INDEX idx_transactions_date ON transactions(date_transaction);
CREATE INDEX idx_logs_date ON logs(date_log);
CREATE INDEX idx_logs_type ON logs(type_event);

CREATE OR REPLACE FUNCTION hash_password(plain_password TEXT)
RETURNS TEXT LANGUAGE plpgsql AS $$
BEGIN
    IF plain_password IS NULL OR length(plain_password) < 10 THEN
        RAISE EXCEPTION 'Le mot de passe doit contenir au moins 10 caracteres';
    END IF;
    RETURN crypt(plain_password, gen_salt('bf', 12));
END;
$$;

CREATE OR REPLACE FUNCTION verify_password(plain_password TEXT, stored_hash TEXT)
RETURNS BOOLEAN LANGUAGE SQL AS $$
    SELECT crypt(plain_password, stored_hash) = stored_hash;
$$;

CREATE OR REPLACE FUNCTION hash_sensitive_value(plain_value TEXT)
RETURNS TEXT LANGUAGE plpgsql AS $$
BEGIN
    IF plain_value IS NULL OR trim(plain_value) = '' THEN
        RETURN NULL;
    END IF;
    RETURN crypt(plain_value, gen_salt('bf', 12));
END;
$$;

CREATE OR REPLACE FUNCTION creer_compte(
    p_prenom VARCHAR,
    p_nom VARCHAR,
    p_email VARCHAR,
    p_password TEXT,
    p_numero_tel VARCHAR DEFAULT NULL,
    p_adresse TEXT DEFAULT NULL
)
RETURNS UUID LANGUAGE plpgsql AS $$
DECLARE
    v_id_user UUID;
    v_id_compte UUID;
BEGIN
    IF p_email IS NULL OR trim(p_email) = '' THEN
        RAISE EXCEPTION 'Une adresse email est obligatoire';
    END IF;

    INSERT INTO utilisateurs(prenom, nom)
    VALUES (trim(p_prenom), trim(p_nom))
    RETURNING id_user INTO v_id_user;

    INSERT INTO comptes(id_user, email, numero_tel, password_hash, adresse)
    VALUES (
        v_id_user,
        lower(trim(p_email)),
        p_numero_tel,
        hash_password(p_password),
        p_adresse
    )
    RETURNING id_compte INTO v_id_compte;

    INSERT INTO logs(id_compte, type_event, niveau, description)
    VALUES (v_id_compte, 'ACCOUNT_CREATED', 'INFO', 'Creation du compte utilisateur');

    RETURN v_id_compte;
END;
$$;

CREATE OR REPLACE FUNCTION ajouter_compte_bancaire(
    p_id_compte UUID,
    p_iban_reference VARCHAR,
    p_solde NUMERIC DEFAULT 0,
    p_devise CHAR(3) DEFAULT 'EUR'
)
RETURNS UUID LANGUAGE plpgsql AS $$
DECLARE
    v_id UUID;
BEGIN
    INSERT INTO comptes_bancaires(id_compte, iban_reference, solde, devise)
    VALUES (p_id_compte, p_iban_reference, p_solde, upper(p_devise))
    RETURNING id_compte_bancaire INTO v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION ajouter_carte(
    p_id_compte_bancaire UUID,
    p_card_token VARCHAR,
    p_numero_carte TEXT,
    p_nom_carte TEXT,
    p_expiration TEXT
)
RETURNS UUID LANGUAGE plpgsql AS $$
DECLARE
    v_id UUID;
BEGIN
    IF p_numero_carte IS NULL OR p_numero_carte !~ '^[0-9]{12,19}$' THEN
        RAISE EXCEPTION 'Numero de carte invalide';
    END IF;

    INSERT INTO cartes(
        id_compte_bancaire, card_token, card_last4,
        numero_carte_hash, nom_carte_hash, expiration_hash
    )
    VALUES (
        p_id_compte_bancaire, p_card_token, right(p_numero_carte, 4),
        hash_sensitive_value(p_numero_carte),
        hash_sensitive_value(p_nom_carte),
        hash_sensitive_value(p_expiration)
    )
    RETURNING id_carte INTO v_id;
    RETURN v_id;
END;
$$;

COMMIT;
