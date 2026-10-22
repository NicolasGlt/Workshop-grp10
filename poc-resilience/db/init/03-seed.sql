-- =====================================================================
-- Données de démo.
--   1) Comptes passerelle : un compte "système" (entrées externes réseau carte)
--      et le compte du marchand (la boutique de café) + sa clé API.
--   2) Jeu de démo du collègue (Alice / Bob, comptes bancaires, carte, transaction).
-- =====================================================================

-- 1) Passerelle PayPoc
DO $$
DECLARE
    v_sys       UUID;
    v_sys_bank  UUID;
    v_shop      UUID;
    v_shop_bank UUID;
BEGIN
    -- Compte système représentant les fonds entrants (réseau carte / monde extérieur)
    v_sys := creer_compte('PayPoc', 'Gateway', 'gateway@paypoc.local',
                          'Gateway_System_2026!', NULL, NULL);
    v_sys_bank := ajouter_compte_bancaire(v_sys, 'EXTERNAL-GATEWAY', 0, 'EUR');

    -- Marchand : la boutique de café
    v_shop := creer_compte('Brulerie', 'du Comptoir', 'shop@brulerie.local',
                           'Shop_Comptoir_2026!', NULL, 'Paris');
    v_shop_bank := ajouter_compte_bancaire(v_shop, 'FR-SHOP-COMPTOIR-001', 0, 'EUR');

    -- Clé API : valeur provisoire, remplacée par MERCHANT_API_KEY du .env (06-merchant-key.sh).
    -- Aucune clé réelle dans le dépôt.
    INSERT INTO merchants(name, api_key, id_compte_bancaire)
    VALUES ('Brulerie du Comptoir', 'pk_placeholder_' || gen_random_uuid(), v_shop_bank);
END $$;

-- 2) Jeu de démo du collègue (comptes utilisateurs classiques)
DO $$
DECLARE
    v_alice UUID;
    v_bob UUID;
    v_bank_alice UUID;
    v_bank_bob UUID;
    v_card_alice UUID;
BEGIN
    SELECT creer_compte('Alice', 'Martin', 'alice@example.com',
        'Alice_Test_2026!', '0600000001', 'Montpellier') INTO v_alice;
    SELECT creer_compte('Bob', 'Dupont', 'bob@example.com',
        'Bob_Test_2026!', '0600000002', 'Montpellier') INTO v_bob;

    SELECT ajouter_compte_bancaire(v_alice, 'TEST-FR-ALICE-001', 1000.00, 'EUR') INTO v_bank_alice;
    SELECT ajouter_compte_bancaire(v_bob, 'TEST-FR-BOB-001', 500.00, 'EUR') INTO v_bank_bob;

    SELECT ajouter_carte(v_bank_alice, 'tok_test_alice_001',
        '4242424242424242', 'ALICE MARTIN', '12/30') INTO v_card_alice;

    INSERT INTO transactions(
        id_compte_emetteur, id_compte_recepteur, id_carte,
        montant, devise, statut, reference_banque, description
    ) VALUES (
        v_bank_alice, v_bank_bob, v_card_alice,
        25.00, 'EUR', 'COMPLETED', 'BANK-TEST-0001', 'Transaction de demonstration'
    );
END $$;
