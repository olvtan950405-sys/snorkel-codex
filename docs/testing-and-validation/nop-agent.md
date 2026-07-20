## NOP Agent (No Operation)

The **NOP Agent** (No Operation) is a baseline agent that performs **no work**. It serves as the **lower-bound performance baseline** for Harbor evaluations.

The NOP agent is used for **benchmarking** to validate that an evaluation pipeline is wired correctly and that failures are not caused by agent execution itself.

- **No setup**  
  Does not install dependencies or perform any environment initialization.

- **No execution**  
  Does not process the instruction or execute any task logic.

- **No results**  
  Returns immediately with an empty context after running the `test.sh` file.

- **0% success rate (expected)**  
  By definition, the NOP agent solves nothing. All task evaluations are expected to **fail**, and this failure is considered a **pass** for the CI step.  
  If the NOP agent passes a task, the task definition or evaluation logic is likely incorrect.

- **CI behavior**  
  If the NOP agent completes evaluation successfully (i.e., fails all tasks as expected), subsequent agents can run without requiring execution of the user’s `solve.sh` file.
