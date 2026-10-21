-- =====================================================================
-- Objets propres à la passerelle PayPoc, ajoutés au modèle bancaire du collègue.
-- On NE modifie pas ses tables : on ajoute seulement ce qu'il faut pour brancher
-- la boutique (identité marchand + compte bancaire de réception).
-- =====================================================================

CREATE TABLE merchants (
    id_merchant         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(140) NOT NULL,
    api_key             VARCHAR(80)  NOT NULL UNIQUE,
    -- compte bancaire (modèle du collègue) sur lequel le marchand encaisse
    id_compte_bancaire  UUID NOT NULL REFERENCES comptes_bancaires(id_compte_bancaire) ON DELETE RESTRICT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_merchants_apikey ON merchants(api_key);

-- Commandes boutique (achat invité). Rattachées au marchand et à la transaction
-- qui les règle ; PAS à un compte bancaire (l'acheteur est un invité).
-- Les coordonnées de livraison sont de simples colonnes.
CREATE TABLE commandes (
    id_commande    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reference      VARCHAR(140) NOT NULL,
    id_merchant    UUID NOT NULL REFERENCES merchants(id_merchant) ON DELETE RESTRICT,
    id_transaction UUID REFERENCES transactions(id_transaction) ON DELETE SET NULL,
    -- Compte client (optionnel) : rempli si l'acheteur était connecté ; NULL pour un invité.
    id_compte      UUID REFERENCES comptes(id_compte) ON DELETE SET NULL,
    client_nom     VARCHAR(140),
    client_email   VARCHAR(255),
    adresse        TEXT,
    code_postal    VARCHAR(20),
    ville          VARCHAR(140),
    montant        NUMERIC(15,2) NOT NULL CHECK (montant > 0),
    devise         CHAR(3) NOT NULL DEFAULT 'EUR',
    statut         VARCHAR(30) NOT NULL DEFAULT 'PAID'
        CHECK (statut IN ('PENDING', 'PAID', 'DECLINED')),   -- PENDING = en attente de validation bancaire (3DS)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_commandes_merchant ON commandes(id_merchant);
CREATE INDEX idx_commandes_transaction ON commandes(id_transaction);
CREATE INDEX idx_commandes_compte ON commandes(id_compte);
CREATE INDEX idx_commandes_date ON commandes(created_at);
