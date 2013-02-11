targets="state_machine.pdf"

state:
	dot -Tpdf -o state_machine.pdf state_machine.dot

clean:
	rm ${targets}
