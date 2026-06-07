# Getting Started with Skill Form

**Skill Form** lets you design interactive forms for SKILL automation without writing code. Here's how to get started:

## Designer Workflow

1. **Drag components** from the left palette (Text, Checkbox, Dropdown, etc.) onto the center canvas.
2. **Arrange and resize** by dragging component edges. Use the grid for alignment.
3. **Configure properties** by clicking a component and editing its settings on the right panel.
4. **Save your work** as a JSON file using the Save button.
5. **Test your form** by clicking Run to switch to Form Runner.

## Common Component Types

- **Text** - Single-line text input
- **Number** - Numeric input with validation
- **Checkbox** - Boolean toggle (multiple allowed)
- **Radio** - Mutually exclusive options
- **Dropdown** - Selection from a list
- **Textarea** - Multi-line text area
- **Date** - Date picker
- **File Path** - File selection dialog
- **List/Board** - Table of rows (supports add/edit/delete)
- **Button** - Action button (trigger custom logic)

## Tips

- Use **Label** components for headers or instructions.
- Use **Separator** to visually divide sections.
- Set required fields in the properties to enforce data validation.
- The **List** component is powerful for tabular data—configure columns in properties.
- Click **Code** to view execution code examples for Shell, Python, and SKILL platforms.

## Using the Results

When a user submits the form in Form Runner, the result is output as JSON. You can copy this JSON and use it in your SKILL automation scripts, store it in a database, or feed it to other tools.
