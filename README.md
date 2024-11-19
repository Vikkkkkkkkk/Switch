1 2 3

VADUVA VICTOR-NICOLAE 332CD

In aceasta tema am implementat un switch ce suporta VLAN si foloseste protocolul STP.

1. Pentru partea de comutare, am folosit structura de dictionar din Python pentru a retine tabela de comutare atunci cand primeam un pachet de la o sursa noua.  
Daca adresa de destinatie este broadcast, facem flooding catre toate celelalte porturi din retea. Altfel, daca adresa de destinatie este in tabela de comutare, trimitem pachetul catre portul corespunzator. Daca nu este in tabela de comutare, facem flooding.  
La aceasta parte am implementat functiile `add_mac_to_table()` si `broadcast()`.

2. Pentru partea de VLAN, am folosit un dictionar pentru a retine tipul de retea de pe fiecare port (trunk sau access).  
Am modificat codul de la prima parte pentru a face verificarile necesare de VLAN, tinand cont de tipul de port pe care a venit pachetul si de tipul de port pe care urmeaza sa il trimitem. Aceste verificari sunt necesare pentru a adauga sau elimina header-ul 802.1Q.  
Am creat functia `parse_switch_config()` pentru a citi configuratia switch-ului si a o retine in dictionarul `config`.

3. Pentru partea de STP, mai intai am creat functiile `create_ethernet_frame()` si `parse_ethernet_frame()` pentru a crea si parsa cadre BPDU.
Apoi trebuie sa initializam switch-ul astfel incat toate port-urile trunk ale acestuia sa fie designated.  
In fiecare secunda, switch-ul trimite un cadru BPDU pe toate porturile trunk prin intermediul functiei `send_bdpu_every_sec()`.  
Daca primeste un cadru BPDU de la un alt switch, verifica daca acesta are bridge ID-ul mai mic decat al sau, caz in care sender-ul devine root, iar switch-ul curent trimite mai departe pachetul.  
Daca pachetul a venit de la un switch cu bridge ID-ul egal cu root-ul actual, se verifica lungimea drumului pana la root si se actualizeaza daca este cazul.  
Pachetul BPDU va contine root BID, BID-ul sender-ului si lungimea drumului pana la root.
