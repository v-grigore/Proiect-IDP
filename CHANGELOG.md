    # Changelog

    Toate modificarile notabile ale proiectului EventFlow sunt documentate in acest fisier.

    Formatul este bazat pe [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), iar versiunile sunt grupate cronologic in functie de etapele de dezvoltare ale proiectului.

    ## [Unreleased]

    ### Planned
    - Stabilizarea fluxului complet de demo dupa rularea stack-ului in Docker Swarm.
    - Completarea documentatiei finale de prezentare cu capturi si rezultate de testare.
    - Eventuale ajustari de securitate pentru parole, secrete si configurari folosite doar pentru demo local.

    ## [0.4.0] - 2026-04-26

    ### Added
    - Documentatie extinsa pentru arhitectura EventFlow, cerinte, rulare, testare si componente.
    - Diagrama de arhitectura si scripturi pentru generarea materialelor de prezentare.
    - Kong API Gateway pentru rutarea traficului catre microservicii.
    - Serviciu dedicat `auth-service` pentru verificare JWT si proxy catre token endpoint-ul Keycloak.
    - Serviciu `data-service` pentru agregare date cross-servicii.
    - Stack de monitorizare cu Prometheus si Grafana.
    - pgAdmin si Portainer ca servicii suport pentru administrare si observabilitate.
    - Pipeline CI in `.github/workflows/ci.yml`.

    ### Changed
    - Extinderea `docker-stack.yml` cu retele separate pentru edge, intern, date, DB si monitorizare.
    - Configurarea serviciilor pentru comunicare prin DNS Docker Swarm si variabile de mediu.
    - Adaugarea replicarii pentru mai multe microservicii, inclusiv `ticketing-service`.
    - Imbunatatirea configurarii Keycloak prin realm-ul `eventflow`.

    ### Fixed
    - Corectii si stabilizari pentru configuratiile Docker, Keycloak, Redis, RabbitMQ si serviciile Flask.
    - Ajustari pentru integrarea frontend-backend in demo local.

    ### Contributions
    - Grigore Vlad: coordonare arhitectura distribuita, structurare livrabile, documentatie tehnica, validare cerinte IDP/SCD si integrare infrastructura de rulare.
    - Barbu Robert: implementare si extindere microservicii, integrare frontend, fluxuri functionale de ticketing/plata/scanare si corectii de stabilitate.

    ## [0.3.0] - 2026-04-19

    ### Added
    - `ticketing-service` pentru managementul evenimentelor, biletelor, waitlist-ului si banlist-ului.
    - `payment-service` pentru sesiuni de plata simulate, rezervare temporara de loc si confirmare/cancel.
    - `gate-service` pentru scanarea si validarea biletelor la intrare.
    - `notification-service` pentru consum RabbitMQ si expunerea notificarilor prin REST.
    - Integrare RabbitMQ pentru notificari asincrone la cumparare si scanare bilet.
    - Redis pentru rate limiting distribuit si caching.
    - Unit tests pentru rate limiting si cache in `ticketing-service`.
    - Schema PostgreSQL extinsa cu evenimente, bilete, waitlist, utilizatori banati, sesiuni de plata si notificari.

    ### Changed
    - Extinderea frontend-ului pentru fluxuri de creare eveniment, cumparare bilet, plata, scanare si notificari.
    - Separarea responsabilitatilor pe servicii specializate, in locul unei implementari monolitice.
    - Adaugarea headerelor si comportamentului de cache pentru citiri publice de evenimente.

    ### Fixed
    - Corectii pentru fluxul de plata cu expirare la 2 minute.
    - Ajustari pentru serializarea datelor si formatul timestamp-urilor catre frontend.
    - Stabilizarea rate limiting-ului pentru rulare pe replici multiple.

    ### Contributions
    - Grigore Vlad: analiza cerintelor pentru functionalitati avansate, validare integrare distribuita, testare scenarii de demo si documentarea deciziilor de arhitectura.
    - Barbu Robert: implementare `ticketing-service`, `payment-service`, `gate-service`, `notification-service`, Redis rate limiting/cache si integrare cu frontend-ul.

    ## [0.2.0] - 2026-04-12

    ### Added
    - Frontend React/Vite pentru interactiunea cu platforma EventFlow.
    - Integrare initiala cu Keycloak pentru autentificare prin token JWT.
    - Fluxuri UI pentru listare evenimente, gestionare token si interactiuni de baza cu API-urile.
    - Primele functionalitati extinse peste scheletul initial al proiectului.

    ### Changed
    - Imbunatatirea structurii proiectului pentru separarea frontend-ului de serviciile backend.
    - Pregatirea aplicatiei pentru fluxuri cu roluri diferite: `ADMIN`, `ORGANIZER`, `ATTENDEE`, `STAFF`.

    ### Fixed
    - Corectii initiale pentru integrarea frontend cu endpoint-urile backend locale.

    ### Contributions
    - Grigore Vlad: definirea scenariilor functionale, revizuire cerinte si validare roluri/fluxuri.
    - Barbu Robert: implementare frontend initial si conectare la serviciile backend disponibile.

    ## [0.1.0] - 2025-04-05

    ### Added
    - Structura initiala a proiectului EventFlow.
    - Functionalitati de baza pentru platforma web de organizare evenimente.
    - Configurare initiala pentru Keycloak, PostgreSQL si servicii backend.
    - `user-profile-service` pentru profil utilizator si management de roluri.
    - Schema initiala de baza de date si fisiere Docker pentru rulare locala.

    ### Contributions
    - Grigore Vlad: definirea temei EventFlow, identificarea cerintelor de proiect si planificarea arhitecturii distribuite.
    - Barbu Robert: implementare initiala a structurii de cod, servicii backend si configuratii de baza.
