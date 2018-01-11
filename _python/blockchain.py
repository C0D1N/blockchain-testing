import hashlib
import json
from time import time
from urllib.parse import urlparse
from uuid import uuid4

import requests
from flask import Flask, jsonify, request


class Blockchain:
    def __init__(self):
        self.current_transactions = []
        self.chain = []
        self.nodes = set()

        # genesis block genereren
        self.new_block(previous_hash='1', proof=100)

    def register_node(self, address):
        """
        Nieuwe node toevoegen aan lijst van NODES
        :param address: Adres van node bv. 'http://192.168.0.5:5000'
        """

        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def valid_chain(self, chain):
        """
        bepalen of een blockchain valide is
        :param chain: een blockchain
        :return: True als correct, False indien niet correct
        """

        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n-----------\n")
            # Checken of de hash van de block correct is
            if block['previous_hash'] != self.hash(last_block):
                return False

            # Checken of POW correct is
            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        Dit is de consensus algorithm, conflicten worden opgelost door de chain te vervangen met de langste in het netwerk.
        :return: True als de chain was vervangen, False indien niet vervangen
        """

        neighbours = self.nodes
        new_chain = None

        # alleen kijken naar langere chaines dan eigen chains
        max_length = len(self.chain)

        # alle chains in de nodes uit ons netwerk ophalen en verifieren 
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # Controleer of de lengte langer is en of de chain geldig is
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # Vervang de chain als we achterhalen dat er een nieuwe gelidige en langere chain is dan de huidige
        if new_chain:
            self.chain = new_chain
            return True

        return False

    def new_block(self, proof, previous_hash):
        """
        Maak een nieuwe block op de blockchain
        :param proof: De proof gegeven door de POW algoritme
        :param previous_hash: Hash van de vorige block
        :return: nieuwe block
        """

        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }

        # Huidige lijst van transacties resetten
        self.current_transactions = []

        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        """
        Maakt een nieuwe transactie in de volgende geminde block
        :param sender: Adres van verzender
        :param recipient: Adres of the ontvanger
        :param amount: hoeveelheid
        :return: De index van de block die de transactie bevat
        """
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })

        return self.last_block['index'] + 1

    @property
    def last_block(self):
        return self.chain[-1]

    @staticmethod
    def hash(block):
        """
        maakt een SHA-256 hash van een Block
        :param block: Block
        """

        # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def proof_of_work(self, last_proof):
        """
        Simple POW Algoritme:
         - Vind een nummer p' zodat hash(pp') meer dan 4 nullen heeft, waar p de vroige p is'
         - p is de vorige proof, en p' is de nieuwe proof
        """

        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1

        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        """
        Valideert dee Proof
        :param last_proof: vorige Proof
        :param proof: huidige Proof
        :return: True als correct, False indien niet correct.
        """

        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"


# Instanteer de node
app = Flask(__name__)

# Genereer een globaal uniek adres voor deze node
node_identifier = str(uuid4()).replace('-', '')

# Instanteer de Blockchain
blockchain = Blockchain()


@app.route('/mine', methods=['GET'])
def mine():
    # Uitvoeren van POW algoritme om de volgende proof op te halen...
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # We moeten een beloning ontvangen voor het vinden van een proof.
    # De zender is "0" voor de signalering dat de node een nieuwe coin heeeeft gemined.
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1,
    )

    # Forge de nieuwe Block door het toe te voegen aan de chain
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message': "Nieuwe Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }
    return jsonify(response), 200


@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()

    # Controleren of alle nodige data in de POST aanwezig is
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Data ontbreekt', 400

    # Maak nieuwe transactie
    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {'message': f'Transactie zal toegevoegd worden aan block {index}'}
    return jsonify(response), 201


@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()

    nodes = values.get('nodes')
    if nodes is None:
        return "Error: Geef een geldige lijst van nodes op", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'Nieuwe nodes zijn toegevoegd',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'onze chain is vervangen',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'onze chain is authoritair',
            'chain': blockchain.chain
        }

    return jsonify(response), 200


if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='luister poort')
    args = parser.parse_args()
    port = args.port

app.run(host='0.0.0.0', port=port)