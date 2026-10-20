DO $$
DECLARE
    v_alice UUID;
    v_bob UUID;
    v_bank_alice UUID;
    v_bank_bob UUID;
    v_card_alice UUID;
BEGIN
    SELECT creer_compte(
        'Alice', 'Martin', 'alice@example.com',
        'Alice_Test_2026!', '0600000001', 'Montpellier'
    ) INTO v_alice;

    SELECT creer_compte(
        'Bob', 'Dupont', 'bob@example.com',
        'Bob_Test_2026!', '0600000002', 'Montpellier'
    ) INTO v_bob;

    SELECT ajouter_compte_bancaire(v_alice, 'TEST-FR-ALICE-001', 1000.00, 'EUR')
    INTO v_bank_alice;

    SELECT ajouter_compte_bancaire(v_bob, 'TEST-FR-BOB-001', 500.00, 'EUR')
    INTO v_bank_bob;

    SELECT ajouter_carte(
        v_bank_alice,
        'tok_test_alice_001',
        '4242424242424242',
        'ALICE MARTIN',
        '12/30'
    ) INTO v_card_alice;

    INSERT INTO transactions(
        id_compte_emetteur, id_compte_recepteur, id_carte,
        montant, devise, statut, reference_banque, description
    ) VALUES (
        v_bank_alice, v_bank_bob, v_card_alice,
        25.00, 'EUR', 'COMPLETED', 'BANK-TEST-0001',
        'Transaction de demonstration'
    );
END;
$$;
