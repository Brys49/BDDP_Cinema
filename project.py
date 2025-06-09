from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from datetime import datetime
import sys
import time
import threading
import random

current_user = None
NODE_1_IP = ["172.22.0.2"] # IP for Node 1 (to check use: docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' cinema-node1)
NODE_2_IP = ["172.22.0.3"] # as above (cinema-node2)

def choose_node():
    print("Select Cassandra node to connect to:")
    print("1. Node 1")
    print("2. Node 2")
    choice = input("Enter choice [1 or 2]: ").strip()

    if choice == "1":
        return NODE_1_IP 
    elif choice == "2":
        return NODE_2_IP 
    else:
        print("Invalid choice, defaulting to Node 1")
        return NODE_1_IP

def connect_to_cluster():
    contact_points = choose_node()
    cluster = Cluster(contact_points)
    session = cluster.connect()
    print("==================================")
    print(f"Connected to {contact_points[0]}")
    return cluster, session


def stress_test_1(session):
    print("==================================")
    print("\n Starting Stress Test 1: The client makes the same request very quickly")

    show_id = input("Enter Show ID for test: ")
    seat_id = input("Enter Seat ID to reserve: ")
    user_id = input("Enter User ID: ")
    try:
        attempts = int(input("Enter number of attempts: "))
    except ValueError:
        print("Invalid number")
        return

    start_time = time.time()
    success = 0
    fail = 0
    reservation_time = datetime.now()

    for i in range(attempts):
        query = """
        INSERT INTO reservations (show_id, seat_id, user_id, reservation_time)
        VALUES (?, ?, ?, ?)
        IF NOT EXISTS
        """
        prepared = session.prepare(query)
        result = session.execute(prepared, (show_id, seat_id, user_id, reservation_time))

        if result.one().applied:
            success += 1
            print(f"Attempt {i+1}: Reservation successful")
        else:
            fail += 1
            print(f"Attempt {i+1}: Seat already reserved")

    end_time = time.time()
    print("\n Stress Test Complete")
    print(f"Successful reservations: {success}")
    print(f"Failed attempts: {fail}")
    print(f"Time: {end_time - start_time:.2f} seconds")


def stress_test_2(session):
    print("==================================")
    print("\n Starting Stress Test 2: Two or more clients make the possible requests randomly")

    try:
        num_clients = int(input("Enter number of simulated clients (2 or more): "))
        num_requests = int(input("Enter number of requests per client: "))
    except ValueError:
        print("Invalid input")
        return

    show_ids = ["show1", "show2", "show3"]
    seat_ids = [f"A{i}" for i in range(1, 11)]

    results_summary = {}

    def simulate_client(client_id):
        success = 0
        fail = 0
        user_id = f"user_{client_id}"
        prepared = session.prepare("""
            INSERT INTO reservations (show_id, seat_id, user_id, reservation_time)
            VALUES (?, ?, ?, ?)
            IF NOT EXISTS
        """)

        for _ in range(num_requests):
            show_id = random.choice(show_ids)
            seat_id = random.choice(seat_ids)
            reservation_time = datetime.now()

            result = session.execute(prepared, (show_id, seat_id, user_id, reservation_time))
            if result.one().applied:
                success += 1
                print(f"[Client {client_id}] Reserved {seat_id} in {show_id}")
            else:
                fail += 1
                print(f"[Client {client_id}] Seat {seat_id} in {show_id} already taken")

        results_summary[client_id] = {"success": success, "fail": fail}

    threads = []
    for client_id in range(1, num_clients + 1):
        t = threading.Thread(target=simulate_client, args=(client_id,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("\n Stress Test 2 Summary:")
    for cid in sorted(results_summary):
        stats = results_summary[cid]
        print(f"Client {cid} -> Success: {stats['success']}, Failed: {stats['fail']}")


def stress_test_3():
    print("==================================")
    print("\n Starting Stress Test 3: Immediate occupancy of all seats/reservations on 2 clients")

    show_id = "show_Stress_Test_3"
    seat_ids = [f"A{i}" for i in range(1, 21)]
    summary = {1: 0, 2: 0}

    cluster1 = Cluster(NODE_1_IP)
    session1 = cluster1.connect()
    session1.set_keyspace('cinema')

    cluster2 = Cluster(NODE_2_IP)
    session2 = cluster2.connect()
    session2.set_keyspace('cinema')

    prepared1 = session1.prepare("""
        INSERT INTO reservations (show_id, seat_id, user_id, reservation_time)
        VALUES (?, ?, ?, ?)
        IF NOT EXISTS
    """)

    prepared2 = session2.prepare("""
        INSERT INTO reservations (show_id, seat_id, user_id, reservation_time)
        VALUES (?, ?, ?, ?)
        IF NOT EXISTS
    """)

    def reserve_all(session, prepared, client_id):
        user_id = f"user_{client_id}"
        for seat_id in seat_ids:
            time.sleep(random.uniform(0.01, 0.05)) 
            try:
                result = session.execute(prepared, (show_id, seat_id, user_id, datetime.now()))
                if result.one().applied:
                    summary[client_id] += 1
                    print(f"[Client {client_id}] Reserved {seat_id}")
                else:
                    print(f"[Client {client_id}] {seat_id} already taken")
            except Exception as e:
                print(f"[Client {client_id}] Error reserving {seat_id}: {e}")

    t1 = threading.Thread(target=reserve_all, args=(session1, prepared1, 1))
    t2 = threading.Thread(target=reserve_all, args=(session2, prepared2, 2))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    print("\n Stress Test 3 Summary:")
    print(f"Client 1 -> Reserved Seats: {summary[1]}")
    print(f"Client 2 -> Reserved Seats: {summary[2]}")

    if summary[1] > 0 and summary[2] > 0:
        print("Both clients successfully made some reservations. Test PASSED.")
    else:
        print("One client reserved everything. Test FAILED.")

    cluster1.shutdown()
    cluster2.shutdown()


def clear_reservations(session):
    print("==================================")
    confirm = input("Are you sure you want to delete ALL reservations? (yes/no): ").lower()
    if confirm == "yes":
        try:
            session.execute("TRUNCATE reservations")
            print("All reservations have been cleared.")
        except Exception as e:
            print(f"Error clearing reservations: {e}")
    else:
        print("ℹ️ Clear operation canceled.")


# Function: Make a reservation
def make_reservation(session, show_id, seat_id, user_id):
    reservation_time = datetime.now()
    query = """
    INSERT INTO reservations (show_id, seat_id, user_id, reservation_time)
    VALUES (?, ?, ?, ?)
    IF NOT EXISTS
    """
    prepared = session.prepare(query)
    result = session.execute(prepared, (show_id, seat_id, user_id, reservation_time))
    
    if result.one().applied:
        print(f"Reservation successful for seat {seat_id} in show {show_id}.")
    else:
        print(f"Seat {seat_id} is already reserved.")


def view_reservations(session, show_id):
    query = "SELECT seat_id, user_id, reservation_time FROM reservations WHERE show_id = %s"
    rows = session.execute(query, (show_id,))
    
    print(f"\n Reservations for show {show_id}:")
    for row in rows:
        print(f"Seat: {row.seat_id}, User: {row.user_id}, Time: {row.reservation_time}")


def update_reservation(session, show_id, old_seat_id, new_seat_id, user_id):
    select_query = "SELECT user_id FROM reservations WHERE show_id = %s AND seat_id = %s"
    result = session.execute(select_query, (show_id, old_seat_id))

    if not result.one():
        print("No reservation found for that seat.")
        return

    if result.one().user_id != user_id:
        print("You can only update your own reservations.")
        return

    reservation_time = datetime.now()
    insert_query = """
    INSERT INTO reservations (show_id, seat_id, user_id, reservation_time)
    VALUES (%s, %s, %s, %s)
    IF NOT EXISTS
    """
    insert_result = session.execute(insert_query, (show_id, new_seat_id, user_id, reservation_time))
    if not insert_result.one().applied:
        print("New seat is already taken.")
        return

    delete_query = "DELETE FROM reservations WHERE show_id = %s AND seat_id = %s"
    session.execute(delete_query, (show_id, old_seat_id))
    print(f"Seat updated from {old_seat_id} to {new_seat_id}")



def view_my_reservations(session, user_id):
    query = "SELECT show_id, seat_id, reservation_time FROM reservations WHERE user_id = %s ALLOW FILTERING"
    rows = session.execute(query, (user_id,))
    
    print(f"\n Reservations for user '{user_id}':")
    for row in rows:
        print(f"Show: {row.show_id}, Seat: {row.seat_id}, Time: {row.reservation_time}")


def view_all_reservations(session, show_id):
    query = "SELECT seat_id, user_id, reservation_time FROM reservations WHERE show_id = %s"
    rows = session.execute(query, (show_id,))
    
    print(f"\n All reservations for show '{show_id}':")
    for row in rows:
        print(f"Seat: {row.seat_id}, User: {row.user_id}, Time: {row.reservation_time}")


def user_menu(session):
    while True:
        print(f"\n Logged in as: {current_user}")
        print("1. Make Reservation")
        print("2. Update Reservation")
        print("3. View My Reservations")
        print("4. View All Reservations")
        print("5. Logout")
        choice = input("Select option: ")

        if choice == '1':
            print("==================================")
            show_id = input("Enter Show ID: ")
            seat_id = input("Enter Seat ID: ")
            make_reservation(session, show_id, seat_id, current_user)

        elif choice == '2':
            print("==================================")
            show_id = input("Enter Show ID: ")
            old_seat_id = input("Enter Old Seat ID: ")
            new_seat_id = input("Enter New Seat ID: ")
            update_reservation(session, show_id, old_seat_id, new_seat_id, current_user)

        elif choice == '3':
            print("==================================")
            view_my_reservations(session, current_user)

        elif choice == '4':
            print("==================================")
            show_id = input("Enter Show ID: ")
            view_all_reservations(session, show_id)

        elif choice == '5':
            print("==================================")
            print("Logging out...")
            break

        else:
            print("Invalid option")


def main():
    global current_user
    print(""""
          
░█████╗░██╗███╗░░██╗███████╗███╗░░░███╗░█████╗░
██╔══██╗██║████╗░██║██╔════╝████╗░████║██╔══██╗
██║░░╚═╝██║██╔██╗██║█████╗░░██╔████╔██║███████║
██║░░██╗██║██║╚████║██╔══╝░░██║╚██╔╝██║██╔══██║
╚█████╔╝██║██║░╚███║███████╗██║░╚═╝░██║██║░░██║
░╚════╝░╚═╝╚═╝░░╚══╝╚══════╝╚═╝░░░░░╚═╝╚═╝░░╚═╝

██████╗░███████╗░██████╗███████╗██████╗░██╗░░░██╗░█████╗░████████╗██╗░█████╗░███╗░░██╗
██╔══██╗██╔════╝██╔════╝██╔════╝██╔══██╗██║░░░██║██╔══██╗╚══██╔══╝██║██╔══██╗████╗░██║
██████╔╝█████╗░░╚█████╗░█████╗░░██████╔╝╚██╗░██╔╝███████║░░░██║░░░██║██║░░██║██╔██╗██║
██╔══██╗██╔══╝░░░╚═══██╗██╔══╝░░██╔══██╗░╚████╔╝░██╔══██║░░░██║░░░██║██║░░██║██║╚████║
██║░░██║███████╗██████╔╝███████╗██║░░██║░░╚██╔╝░░██║░░██║░░░██║░░░██║╚█████╔╝██║░╚███║
╚═╝░░╚═╝╚══════╝╚═════╝░╚══════╝╚═╝░░╚═╝░░░╚═╝░░░╚═╝░░╚═╝░░░╚═╝░░░╚═╝░╚════╝░╚═╝░░╚══╝

░██████╗██╗░░░██╗░██████╗████████╗███████╗███╗░░░███╗
██╔════╝╚██╗░██╔╝██╔════╝╚══██╔══╝██╔════╝████╗░████║
╚█████╗░░╚████╔╝░╚█████╗░░░░██║░░░█████╗░░██╔████╔██║
░╚═══██╗░░╚██╔╝░░░╚═══██╗░░░██║░░░██╔══╝░░██║╚██╔╝██║
██████╔╝░░░██║░░░██████╔╝░░░██║░░░███████╗██║░╚═╝░██║
╚═════╝░░░░╚═╝░░░╚═════╝░░░░╚═╝░░░╚══════╝╚═╝░░░░░╚═╝
          """)
    
    print(""" 
░█─▄▀ ░█▀▀█ ░█▀▀▀█ ░█──░█ ░█▀▀▀█ ░█▀▀▀█ ▀▀█▀▀ ░█▀▀▀█ ░█▀▀▀ 　 ░█▀▀█ ░█▀▀█ ░█──░█ ░█▀▀▀█ ░█▀▀▀█ ─█▀▀█ ░█─▄▀ 
░█▀▄─ ░█▄▄▀ ─▄▄▄▀▀ ░█▄▄▄█ ─▀▀▀▄▄ ─▄▄▄▀▀ ─░█── ░█──░█ ░█▀▀▀ 　 ░█▀▀▄ ░█▄▄▀ ░█▄▄▄█ ─▀▀▀▄▄ ─▄▄▄▀▀ ░█▄▄█ ░█▀▄─ 
░█─░█ ░█─░█ ░█▄▄▄█ ──░█── ░█▄▄▄█ ░█▄▄▄█ ─░█── ░█▄▄▄█ ░█─── 　 ░█▄▄█ ░█─░█ ──░█── ░█▄▄▄█ ░█▄▄▄█ ░█─░█ ░█─░█
""")
    
    print("""
▄█░ █▀▀ ▄▀▀▄ █▀▀█ █▀▀ █▀█ 
░█░ ▀▀▄ █▄▄░ █▄▀█ ▀▀▄ ░▄▀ 
▄█▄ ▄▄▀ ▀▄▄▀ █▄▄█ ▄▄▀ █▄▄
""")
    cluster, session = connect_to_cluster()
    session.set_keyspace('cinema')

    while True:
        print("==================================")
        print("\n1. Login")
        print("2. Exit")
        print("3. Run Stress Test 1")
        print("4. Run Stress Test 2")
        print("5. Run Stress Test 3")
        print("6. Clear All Reservations")
        choice = input("Select option: ")

        if choice == '1':
            user_id = input("Enter your User ID: ").strip()
            if user_id:
                current_user = user_id
                user_menu(session)
            else:
                print("Invalid User ID")

        elif choice == '2':
            print("Goodbye!")
            break

        elif choice == '3':
            stress_test_1(session)

        elif choice == '4':
            stress_test_2(session)

        elif choice == '5':
            stress_test_3()

        elif choice == '6':
            clear_reservations(session)

        else:
            print("Invalid option")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
